from __future__ import annotations

import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from universal_orchestrator.capacity import CapacityBroker, CapacityReservationError
from universal_orchestrator.models import (
    CapacityDimension,
    CapacitySnapshot,
    CapacityStatus,
    CapacityWindow,
    utc_now,
)
from universal_orchestrator.routing import CapabilityRegistry
from universal_orchestrator.runtime import RuntimeStore


def snapshot(
    *,
    connector_id: str = "provider/default",
    remaining: float | None = 1,
    observed_at=None,
    status: CapacityStatus = CapacityStatus.AVAILABLE,
    windows: list[CapacityWindow] | None = None,
) -> CapacitySnapshot:
    now = observed_at or utc_now()
    return CapacitySnapshot(
        connector_id=connector_id,
        provider_id="provider",
        model_id="model",
        account_scope="account",
        status=status,
        observed_at=now,
        expires_at=now + timedelta(minutes=5),
        windows=windows
        if windows is not None
        else [CapacityWindow(dimension=CapacityDimension.REQUESTS, remaining=remaining)],
    )


class CapacityTruthTests(unittest.TestCase):
    def test_committed_capacity_is_not_reused_against_same_snapshot(self) -> None:
        broker = CapacityBroker()
        broker.update(snapshot(remaining=1))
        first = broker.reserve("R", "T1", "provider/default", {CapacityDimension.REQUESTS: 1})
        broker.commit(first)

        with self.assertRaises(CapacityReservationError):
            broker.reserve("R", "T2", "provider/default", {CapacityDimension.REQUESTS: 1})

    def test_headerless_unknown_observation_does_not_erase_exact_window(self) -> None:
        broker = CapacityBroker()
        first_time = utc_now()
        broker.update(snapshot(observed_at=first_time, remaining=3))
        broker.update(
            snapshot(
                observed_at=first_time + timedelta(seconds=1),
                status=CapacityStatus.UNKNOWN,
                windows=[],
            )
        )

        effective = broker.snapshot("provider/default")
        self.assertIsNotNone(effective)
        assert effective is not None
        self.assertEqual(effective.windows[0].remaining, 3)
        self.assertEqual(broker.latest_observation("provider/default").status, CapacityStatus.UNKNOWN)

    def test_registry_runtime_binding_reaches_the_capacity_broker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = CapabilityRegistry.from_environment()
            runtime = RuntimeStore(Path(directory) / "runtime.sqlite3")

            registry.bind_runtime(runtime)

            self.assertIs(registry.runtime_store, runtime)
            self.assertIs(registry.capacity_broker.runtime_store, runtime)

    def test_subscription_limit_configuration_is_validated(self) -> None:
        with patch.dict(os.environ, {"UO_SUBSCRIPTION_CALL_LIMIT": "not-an-int"}, clear=False):
            with self.assertRaises(ValueError):
                CapacityBroker()


if __name__ == "__main__":
    unittest.main()
