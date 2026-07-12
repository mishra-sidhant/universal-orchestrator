from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from universal_orchestrator.models import (
    CapacitySnapshot,
    HandoffRecord,
    RuntimeEvent,
    TaskCheckpoint,
    TaskLease,
    new_id,
    utc_now,
)
from universal_orchestrator.utils import ensure_dir


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _lease_is_current(conn: sqlite3.Connection, lease: TaskLease) -> bool:
    row = conn.execute(
        """
        SELECT owner_id, lease_id, epoch, status, expires_at
        FROM task_leases WHERE run_id=? AND task_id=?
        """,
        (lease.run_id, lease.task_id),
    ).fetchone()
    if row is None:
        return False
    return (
        row[0] == lease.owner_id
        and row[1] == lease.lease_id
        and int(row[2]) == lease.epoch
        and row[3] == "active"
        and _parse_datetime(row[4]) > utc_now()
    )


class RuntimeStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        ensure_dir(self.path.parent)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_summaries (
                    run_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    artifact_dir TEXT NOT NULL,
                    quality_passed INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_records (
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    cache_key TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, task_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cancellations (
                    run_id TEXT PRIMARY KEY,
                    reason TEXT NOT NULL,
                    requested_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    cache_key TEXT,
                    warnings TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS failure_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS capacity_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    connector_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_leases (
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    epoch INTEGER NOT NULL,
                    attempt INTEGER NOT NULL,
                    acquired_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    PRIMARY KEY(run_id, task_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    sequence INTEGER NOT NULL,
                    lease_epoch INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, task_id, attempt, sequence)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS handoff_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS subscription_capacity (
                    run_id TEXT NOT NULL,
                    connector_id TEXT NOT NULL,
                    used INTEGER NOT NULL,
                    limit_value INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, connector_id)
                )
                """
            )

    def record_event(self, event: RuntimeEvent) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO events(run_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
                (
                    event.run_id,
                    event.event_type,
                    json.dumps(event.payload, sort_keys=True, default=str),
                    event.created_at.isoformat(),
                ),
            )

    def save_run_summary(self, run_id: str, state: str, artifact_dir: str, quality_passed: bool) -> None:
        from universal_orchestrator.models import utc_now

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO run_summaries(run_id, state, artifact_dir, quality_passed, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    state=excluded.state,
                    artifact_dir=excluded.artifact_dir,
                    quality_passed=excluded.quality_passed,
                    updated_at=excluded.updated_at
                """,
                (run_id, state, artifact_dir, int(quality_passed), utc_now().isoformat()),
            )

    def transition(self, run_id: str, state: str) -> None:
        from universal_orchestrator.models import utc_now

        with self._connection() as conn:
            conn.execute(
                "INSERT INTO state_transitions(run_id, state, created_at) VALUES (?, ?, ?)",
                (run_id, state, utc_now().isoformat()),
            )

    def save_task_record(
        self,
        run_id: str,
        task_id: str,
        status: str,
        attempt: int,
        cache_key: str | None,
    ) -> None:
        from universal_orchestrator.models import utc_now

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO task_records(run_id, task_id, status, attempt, cache_key, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, task_id) DO UPDATE SET
                    status=excluded.status,
                    attempt=excluded.attempt,
                    cache_key=excluded.cache_key,
                    updated_at=excluded.updated_at
                """,
                (run_id, task_id, status, attempt, cache_key, utc_now().isoformat()),
            )

    def save_task_attempt(
        self,
        run_id: str,
        task_id: str,
        attempt: int,
        status: str,
        cache_key: str | None,
        warnings: list[str],
    ) -> None:
        from universal_orchestrator.models import utc_now

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO task_attempts(run_id, task_id, attempt, status, cache_key, warnings, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    task_id,
                    attempt,
                    status,
                    cache_key,
                    json.dumps(warnings),
                    utc_now().isoformat(),
                ),
            )

    def save_failure(self, run_id: str, stage: str, error: Exception) -> None:
        from universal_orchestrator.models import utc_now

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO failure_records(run_id, stage, error_type, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, stage, type(error).__name__, str(error), utc_now().isoformat()),
            )

    def save_capacity_snapshot(self, snapshot: CapacitySnapshot) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO capacity_snapshots(connector_id, observed_at, payload) VALUES (?, ?, ?)",
                (
                    snapshot.connector_id,
                    snapshot.observed_at.isoformat(),
                    json.dumps(snapshot.model_dump(mode="json"), sort_keys=True),
                ),
            )

    def reserve_subscription_capacity(
        self, run_id: str, connector_id: str, amount: int, limit: int
    ) -> bool:
        if amount <= 0:
            return True
        with self._connection() as conn:
            row = conn.execute(
                "SELECT used, limit_value FROM subscription_capacity WHERE run_id=? AND connector_id=?",
                (run_id, connector_id),
            ).fetchone()
            used = int(row[0]) if row else 0
            stored_limit = int(row[1]) if row else limit
            effective_limit = min(stored_limit, limit)
            if used + amount > effective_limit:
                return False
            conn.execute(
                """
                INSERT INTO subscription_capacity(run_id, connector_id, used, limit_value, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, connector_id) DO UPDATE SET
                    used=excluded.used,
                    limit_value=excluded.limit_value,
                    updated_at=excluded.updated_at
                """,
                (
                    run_id,
                    connector_id,
                    used + amount,
                    effective_limit,
                    utc_now().isoformat(),
                ),
            )
            return True

    def release_subscription_capacity(self, run_id: str, connector_id: str, amount: int) -> None:
        if amount <= 0:
            return
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE subscription_capacity
                SET used=MAX(0, used-?), updated_at=?
                WHERE run_id=? AND connector_id=?
                """,
                (amount, utc_now().isoformat(), run_id, connector_id),
            )

    def subscription_capacity(self, run_id: str, connector_id: str) -> dict[str, int] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT used, limit_value FROM subscription_capacity WHERE run_id=? AND connector_id=?",
                (run_id, connector_id),
            ).fetchone()
        if row is None:
            return None
        return {"used": int(row[0]), "limit": int(row[1])}

    def latest_capacity_snapshot(self, connector_id: str) -> CapacitySnapshot | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT payload FROM capacity_snapshots WHERE connector_id=? ORDER BY id DESC LIMIT 1",
                (connector_id,),
            ).fetchone()
        if row is None:
            return None
        return CapacitySnapshot.model_validate(json.loads(row[0]))

    def capacity_snapshots(self, connector_id: str | None = None) -> list[CapacitySnapshot]:
        query = "SELECT payload FROM capacity_snapshots"
        params: tuple[str, ...] = ()
        if connector_id is not None:
            query += " WHERE connector_id=?"
            params = (connector_id,)
        query += " ORDER BY id"
        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [CapacitySnapshot.model_validate(json.loads(row[0])) for row in rows]

    def acquire_task_lease(
        self,
        run_id: str,
        task_id: str,
        owner_id: str,
        ttl_seconds: float,
        attempt: int = 1,
    ) -> TaskLease | None:
        now = utc_now()
        expires_at = now + timedelta(seconds=max(0.1, ttl_seconds))
        with self._connection() as conn:
            row = conn.execute(
                "SELECT epoch, status, expires_at FROM task_leases WHERE run_id=? AND task_id=?",
                (run_id, task_id),
            ).fetchone()
            if row is not None and row[1] == "active" and _parse_datetime(row[2]) > now:
                return None
            epoch = int(row[0]) + 1 if row is not None else 1
            lease = TaskLease(
                run_id=run_id,
                task_id=task_id,
                owner_id=owner_id,
                lease_id=new_id("lease"),
                epoch=epoch,
                attempt=attempt,
                acquired_at=now,
                heartbeat_at=now,
                expires_at=expires_at,
            )
            conn.execute(
                """
                INSERT INTO task_leases(
                    run_id, task_id, owner_id, lease_id, epoch, attempt,
                    acquired_at, heartbeat_at, expires_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                ON CONFLICT(run_id, task_id) DO UPDATE SET
                    owner_id=excluded.owner_id,
                    lease_id=excluded.lease_id,
                    epoch=excluded.epoch,
                    attempt=excluded.attempt,
                    acquired_at=excluded.acquired_at,
                    heartbeat_at=excluded.heartbeat_at,
                    expires_at=excluded.expires_at,
                    status='active'
                """,
                (
                    lease.run_id,
                    lease.task_id,
                    lease.owner_id,
                    lease.lease_id,
                    lease.epoch,
                    lease.attempt,
                    lease.acquired_at.isoformat(),
                    lease.heartbeat_at.isoformat(),
                    lease.expires_at.isoformat(),
                ),
            )
            return lease

    def renew_task_lease(self, lease: TaskLease, ttl_seconds: float) -> bool:
        now = utc_now()
        expires_at = now + timedelta(seconds=max(0.1, ttl_seconds))
        with self._connection() as conn:
            cursor = conn.execute(
                """
                UPDATE task_leases
                SET heartbeat_at=?, expires_at=?
                WHERE run_id=? AND task_id=? AND owner_id=? AND lease_id=? AND epoch=? AND status='active'
                """,
                (
                    now.isoformat(),
                    expires_at.isoformat(),
                    lease.run_id,
                    lease.task_id,
                    lease.owner_id,
                    lease.lease_id,
                    lease.epoch,
                ),
            )
        return cursor.rowcount == 1

    def current_task_lease(self, run_id: str, task_id: str, owner_id: str) -> TaskLease | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT owner_id, lease_id, epoch, attempt, acquired_at, heartbeat_at, expires_at
                FROM task_leases
                WHERE run_id=? AND task_id=? AND owner_id=? AND status='active'
                """,
                (run_id, task_id, owner_id),
            ).fetchone()
        if row is None:
            return None
        return TaskLease(
            run_id=run_id,
            task_id=task_id,
            owner_id=row[0],
            lease_id=row[1],
            epoch=int(row[2]),
            attempt=int(row[3]),
            acquired_at=_parse_datetime(row[4]),
            heartbeat_at=_parse_datetime(row[5]),
            expires_at=_parse_datetime(row[6]),
        )

    def release_task_lease(self, lease: TaskLease, status: str = "completed") -> bool:
        with self._connection() as conn:
            cursor = conn.execute(
                """
                UPDATE task_leases SET status=?
                WHERE run_id=? AND task_id=? AND owner_id=? AND lease_id=? AND epoch=? AND status='active'
                """,
                (status, lease.run_id, lease.task_id, lease.owner_id, lease.lease_id, lease.epoch),
            )
        return cursor.rowcount == 1

    def recover_expired_leases(self) -> int:
        now = utc_now().isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE task_leases SET status='abandoned' WHERE status='active' AND expires_at<=?",
                (now,),
            )
        return cursor.rowcount

    def save_checkpoint(self, checkpoint: TaskCheckpoint, lease: TaskLease) -> bool:
        with self._connection() as conn:
            if not _lease_is_current(conn, lease):
                return False
            conn.execute(
                """
                INSERT INTO task_checkpoints(
                    run_id, task_id, attempt, sequence, lease_epoch, payload, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.run_id,
                    checkpoint.task_id,
                    checkpoint.attempt,
                    checkpoint.sequence,
                    checkpoint.lease_epoch,
                    json.dumps(checkpoint.model_dump(mode="json"), sort_keys=True),
                    checkpoint.created_at.isoformat(),
                ),
            )
            return True

    def latest_checkpoint(self, run_id: str, task_id: str) -> TaskCheckpoint | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT payload FROM task_checkpoints WHERE run_id=? AND task_id=? ORDER BY sequence DESC, id DESC LIMIT 1",
                (run_id, task_id),
            ).fetchone()
        return TaskCheckpoint.model_validate(json.loads(row[0])) if row is not None else None

    def next_checkpoint_sequence(self, run_id: str, task_id: str) -> int:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM task_checkpoints WHERE run_id=? AND task_id=?",
                (run_id, task_id),
            ).fetchone()
        return int(row[0]) + 1 if row is not None else 1

    def save_handoff(self, handoff: HandoffRecord) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO handoff_records(run_id, task_id, attempt, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    handoff.run_id,
                    handoff.task_id,
                    handoff.attempt,
                    json.dumps(handoff.model_dump(mode="json"), sort_keys=True),
                    handoff.created_at.isoformat(),
                ),
            )

    def handoffs(self, run_id: str, task_id: str | None = None) -> list[HandoffRecord]:
        query = "SELECT payload FROM handoff_records WHERE run_id=?"
        params: list[str] = [run_id]
        if task_id is not None:
            query += " AND task_id=?"
            params.append(task_id)
        query += " ORDER BY id"
        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [HandoffRecord.model_validate(json.loads(row[0])) for row in rows]

    def latest_state(self, run_id: str) -> str | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT state FROM state_transitions WHERE run_id=? ORDER BY id DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        return row[0] if row else None

    def resumable_snapshot(self, run_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT task_id, status, attempt, cache_key FROM task_records WHERE run_id=? ORDER BY task_id",
                (run_id,),
            ).fetchall()
        return {
            "run_id": run_id,
            "latest_state": self.latest_state(run_id),
            "cancel": self.cancel_status(run_id),
            "tasks": [
                {"task_id": row[0], "status": row[1], "attempt": row[2], "cache_key": row[3]}
                for row in rows
            ],
        }

    def request_cancel(self, run_id: str, reason: str = "User requested cancellation.") -> dict[str, Any]:
        from universal_orchestrator.models import RunState, RuntimeEvent, utc_now

        latest = self.latest_state(run_id)
        terminal_states = {
            RunState.DELIVERED,
            RunState.NEEDS_ATTENTION,
            RunState.FAILED,
            RunState.CANCELLED,
        }
        if latest in terminal_states or str(latest) in {str(state) for state in terminal_states}:
            return {
                "run_id": run_id,
                "accepted": False,
                "cancelled": False,
                "latest_state": latest,
                "reason": f"Run is already terminal: {latest}.",
            }
        requested_at = utc_now().isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO cancellations(run_id, reason, requested_at)
                VALUES (?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    reason=excluded.reason,
                    requested_at=excluded.requested_at
                """,
                (run_id, reason, requested_at),
            )
        self.transition(run_id, RunState.CANCELLED)
        self.record_event(
            RuntimeEvent(
                run_id=run_id,
                event_type="cancel_requested",
                payload={"reason": reason, "requested_at": requested_at},
            )
        )
        return {
            "run_id": run_id,
            "accepted": True,
            "cancelled": True,
            "latest_state": RunState.CANCELLED,
            "reason": reason,
            "requested_at": requested_at,
        }

    def cancel_status(self, run_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT reason, requested_at FROM cancellations WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if not row:
            return {"requested": False}
        return {"requested": True, "reason": row[0], "requested_at": row[1]}

    def is_cancel_requested(self, run_id: str) -> bool:
        return bool(self.cancel_status(run_id).get("requested", False))

    def clear_cancel(self, run_id: str) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM cancellations WHERE run_id=?", (run_id,))

    def latest_successful_summary(self, exclude_run_id: str | None = None) -> dict[str, Any] | None:
        summaries = self.successful_summaries(exclude_run_id=exclude_run_id, limit=1)
        return summaries[0] if summaries else None

    def successful_summaries(
        self,
        exclude_run_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT run_id, state, artifact_dir, quality_passed, updated_at
            FROM run_summaries
            WHERE quality_passed=1
        """
        params: list[Any] = []
        if exclude_run_id:
            query += " AND run_id != ?"
            params.append(exclude_run_id)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "run_id": row[0],
                "state": row[1],
                "artifact_dir": row[2],
                "quality_passed": bool(row[3]),
                "updated_at": row[4],
            }
            for row in rows
        ]

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT run_id, event_type, payload, created_at FROM events WHERE run_id=? ORDER BY id",
                (run_id,),
            ).fetchall()
        return [
            {
                "run_id": row[0],
                "event_type": row[1],
                "payload": json.loads(row[2]),
                "created_at": row[3],
            }
            for row in rows
        ]
