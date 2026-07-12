from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from universal_orchestrator.capacity import CapacityBroker
from universal_orchestrator.handoff import HandoffController
from universal_orchestrator.models import CapacitySnapshot, CapacityStatus
from universal_orchestrator.runtime import RuntimeStore


class HandoffControllerTests(unittest.TestCase):
    def test_handoff_skips_attempted_and_exhausted_connectors(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = RuntimeStore(f"{directory}/runtime.sqlite3")
            capacity = CapacityBroker()
            capacity.update(
                CapacitySnapshot(
                    connector_id="provider-a",
                    provider_id="a",
                    model_id="a-model",
                    account_scope="a",
                    status=CapacityStatus.EXHAUSTED,
                    reason="limit",
                )
            )
            controller = HandoffController(capacity, runtime)

            handoff = controller.choose(
                "R",
                "T",
                attempt=1,
                candidates=["provider-a", "provider-b", "provider-c"],
                attempted_connectors={"provider-b"},
                reason="provider stopped on quota",
                current_connector_id="provider-a",
                checkpoint_sequence=3,
            )

            self.assertIsNotNone(handoff)
            assert handoff is not None
            self.assertEqual(handoff.to_connector_id, "provider-c")
            self.assertEqual(runtime.handoffs("R", "T")[0].reason, "provider stopped on quota")

    def test_handoff_limit_is_honest(self) -> None:
        capacity = CapacityBroker()
        controller = HandoffController(capacity, max_attempts=2, max_handoffs=1)
        first = controller.choose("R", "T", 2, ["a"], set(), "stop")
        self.assertIsNone(first)


if __name__ == "__main__":
    unittest.main()
