from __future__ import annotations

import re
from threading import RLock
from datetime import timedelta
from typing import Mapping

from universal_orchestrator.models import (
    CapacityDimension,
    CapacityReservation,
    CapacitySnapshot,
    CapacityStatus,
    CapacityWindow,
    new_id,
    utc_now,
)


class CapacityReservationError(RuntimeError):
    """A provider cannot safely accept the requested work at this moment."""


class CapacityBroker:
    """Thread-safe in-memory capacity authority for one orchestrator run.

    Providers report observations; the broker owns reservations. Unknown limits
    remain eligible but never behave like unlimited capacity.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, CapacitySnapshot] = {}
        self._reservations: dict[str, CapacityReservation] = {}
        self._lock = RLock()

    def update(self, snapshot: CapacitySnapshot) -> None:
        with self._lock:
            self._snapshots[snapshot.connector_id] = snapshot

    def snapshot(self, connector_id: str) -> CapacitySnapshot | None:
        with self._lock:
            direct = self._snapshots.get(connector_id)
            if direct is not None:
                return direct
            return next(
                (snapshot for snapshot in self._snapshots.values() if snapshot.provider_id == connector_id),
                None,
            )

    def snapshots(self) -> list[CapacitySnapshot]:
        with self._lock:
            return list(self._snapshots.values())

    def is_eligible(self, connector_id: str) -> bool:
        snapshot = self.snapshot(connector_id)
        if snapshot is None:
            return True
        return snapshot.status not in {
            CapacityStatus.EXHAUSTED,
            CapacityStatus.COOLING_DOWN,
            CapacityStatus.UNAVAILABLE,
        }

    def score(self, connector_id: str) -> float:
        snapshot = self.snapshot(connector_id)
        if snapshot is None:
            return 1.0
        return {
            CapacityStatus.AVAILABLE: 1.0,
            CapacityStatus.CONSTRAINED: 0.75,
            CapacityStatus.UNKNOWN: 0.6,
            CapacityStatus.EXHAUSTED: 0.0,
            CapacityStatus.COOLING_DOWN: 0.0,
            CapacityStatus.UNAVAILABLE: 0.0,
        }[snapshot.status]

    def reserve(
        self,
        run_id: str,
        task_id: str,
        connector_id: str,
        dimensions: Mapping[CapacityDimension, float],
    ) -> CapacityReservation:
        requested = {dimension: float(value) for dimension, value in dimensions.items() if value > 0}
        with self._lock:
            snapshot = self._snapshots.get(connector_id)
            if snapshot is not None and not self.is_eligible(connector_id):
                raise CapacityReservationError(
                    f"{connector_id} is {snapshot.status}: {snapshot.reason or 'capacity unavailable'}"
                )
            reserved = self._reserved_for(connector_id)
            windows = {window.dimension: window for window in snapshot.windows} if snapshot else {}
            for dimension, amount in requested.items():
                window = windows.get(dimension)
                if window is None or window.remaining is None:
                    continue
                if reserved.get(dimension, 0.0) + amount > window.remaining:
                    raise CapacityReservationError(
                        f"{connector_id} lacks remaining {dimension.value} capacity "
                        f"for {amount:g} requested units"
                    )
            reservation = CapacityReservation(
                reservation_id=new_id("capacity"),
                run_id=run_id,
                task_id=task_id,
                connector_id=connector_id,
                dimensions=requested,
            )
            self._reservations[reservation.reservation_id] = reservation
            return reservation

    def release(self, reservation: CapacityReservation) -> None:
        with self._lock:
            self._reservations.pop(reservation.reservation_id, None)

    def commit(self, reservation: CapacityReservation) -> None:
        self.release(reservation)

    def active_reservations(self) -> list[CapacityReservation]:
        with self._lock:
            return list(self._reservations.values())

    def _reserved_for(self, connector_id: str) -> dict[CapacityDimension, float]:
        totals: dict[CapacityDimension, float] = {}
        for reservation in self._reservations.values():
            if reservation.connector_id != connector_id:
                continue
            for dimension, amount in reservation.dimensions.items():
                totals[dimension] = totals.get(dimension, 0.0) + amount
        return totals


def snapshot_from_headers(
    *,
    connector_id: str,
    provider_id: str,
    model_id: str,
    account_scope: str,
    headers: Mapping[str, str],
) -> CapacitySnapshot:
    """Normalize common provider rate-limit headers without provider-specific routing logic."""

    normalized = {key.lower(): value.strip() for key, value in headers.items()}
    aliases = {
        CapacityDimension.REQUESTS: (
            ("x-ratelimit-limit-requests", "x-ratelimit-remaining-requests", "x-ratelimit-reset-requests"),
            ("anthropic-ratelimit-requests-limit", "anthropic-ratelimit-requests-remaining", "anthropic-ratelimit-requests-reset"),
        ),
        CapacityDimension.TOTAL_TOKENS: (
            ("x-ratelimit-limit-tokens", "x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens"),
            ("anthropic-ratelimit-tokens-limit", "anthropic-ratelimit-tokens-remaining", "anthropic-ratelimit-tokens-reset"),
        ),
    }
    windows: list[CapacityWindow] = []
    for dimension, families in aliases.items():
        values: tuple[str | None, str | None, str | None] | None = None
        for family in families:
            candidate = tuple(normalized.get(item) for item in family)
            if candidate[0] is not None or candidate[1] is not None:
                values = candidate  # type: ignore[assignment]
                break
        if values is None:
            continue
        limit = _number(values[0])
        remaining = _number(values[1])
        used_percent = None
        if limit is not None and remaining is not None and limit > 0:
            used_percent = max(0.0, min(100.0, ((limit - remaining) / limit) * 100.0))
        reset_seconds = _duration_seconds(values[2])
        windows.append(
            CapacityWindow(
                dimension=dimension,
                limit=limit,
                remaining=remaining,
                used_percent=used_percent,
                reset_at=utc_now() + timedelta(seconds=reset_seconds)
                if reset_seconds is not None
                else None,
            )
        )
    if not windows:
        status = CapacityStatus.UNKNOWN
        reason = "Provider response did not expose a recognized rate-limit window."
    elif any(window.remaining == 0 for window in windows):
        status = CapacityStatus.EXHAUSTED
        reason = "A provider-reported capacity window is exhausted."
    elif any((window.used_percent or 0.0) >= 95.0 for window in windows):
        status = CapacityStatus.EXHAUSTED
        reason = "A provider-reported capacity window is nearly exhausted."
    elif any((window.used_percent or 0.0) >= 80.0 for window in windows):
        status = CapacityStatus.CONSTRAINED
        reason = "A provider-reported capacity window is constrained."
    else:
        status = CapacityStatus.AVAILABLE
        reason = "Provider-reported capacity is available."
    reset_times = [window.reset_at for window in windows if window.reset_at is not None]
    return CapacitySnapshot(
        connector_id=connector_id,
        provider_id=provider_id,
        model_id=model_id,
        account_scope=account_scope,
        status=status,
        source="response_headers",
        confidence=0.95 if windows else 0.25,
        expires_at=min(reset_times) if reset_times else None,
        windows=windows,
        reason=reason,
    )


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _duration_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(ms|s|m|h)\s*", value.lower())
    if not match:
        return None
    amount = float(match.group(1))
    return amount / 1_000 if match.group(2) == "ms" else amount * {
        "s": 1,
        "m": 60,
        "h": 3_600,
    }[match.group(2)]
