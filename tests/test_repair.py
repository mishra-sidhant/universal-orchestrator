import unittest

from universal_orchestrator.models import QualityGateResult, QualityScore
from universal_orchestrator.repair import RepairPlanner
from universal_orchestrator.routing import AdaptiveRouter, CapabilityRegistry


class RepairPlannerTests(unittest.TestCase):
    def test_repair_dag_targets_each_violation_and_validates(self) -> None:
        quality = QualityGateResult(
            passed=False,
            scores=QualityScore(
                completeness=60,
                factuality=80,
                citation_support=70,
                style_quality=80,
                continuity=80,
                cost_efficiency=70,
                artifact_integrity="fail",
                code_validation="not_applicable",
            ),
            violations=["Artifact paths do not exist: ['missing.md']", "Missing routing decisions for tasks: ['T']"],
            repair_task_ids=["T-REPAIR-001", "T-REPAIR-002"],
        )

        dag = RepairPlanner().create_repair_dag("run_test", quality)
        decisions = AdaptiveRouter(CapabilityRegistry.from_environment()).route_all(dag.topological_order())

        self.assertEqual(len(dag.nodes), 3)
        self.assertEqual(dag.nodes[-1].id, "T-REPAIR-VALIDATE")
        self.assertEqual({decision.provider_id for decision in decisions}, {"deterministic.tools"})


if __name__ == "__main__":
    unittest.main()

