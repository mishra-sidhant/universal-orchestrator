import unittest

from universal_orchestrator.models import RoutingAction, RoutingDecision, TaskNode, TaskStatus, TaskType
from universal_orchestrator.workers import StructuredWorkerOutputBuilder


class StructuredWorkerOutputTests(unittest.TestCase):
    def test_degraded_route_records_risk_and_next_action(self) -> None:
        output = StructuredWorkerOutputBuilder().build(
            task=TaskNode(id="T", run_id="R", title="Synthesize", task_type=TaskType.FINAL_SYNTHESIS),
            decision=RoutingDecision(
                task_id="T",
                action=RoutingAction.ROUTE_DEGRADED,
                provider_id="deterministic.tools",
                score=0.7,
                reason="below threshold",
            ),
            provider_result=None,
            context={"consumed_chunk_refs": ["chunk_1"], "files": ["README.md"]},
            status=TaskStatus.COMPLETED,
        )

        self.assertIn("degraded_provider_capability", output["risks"])
        self.assertIn("chunk_1", output["evidence_refs"])
        self.assertTrue(output["next_actions"])


if __name__ == "__main__":
    unittest.main()
