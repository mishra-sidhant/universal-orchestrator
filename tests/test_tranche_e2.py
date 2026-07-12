import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    CostTier,
    HostInvocation,
    ProviderDescriptor,
    ProviderHealth,
    ProviderKind,
    ProviderStatus,
    ProviderTask,
    RoutingAction,
    TaskNode,
    TaskStatus,
    TaskType,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.providers.deterministic import DeterministicToolsAdapter
from universal_orchestrator.routing import AdaptiveRouter, CapabilityRegistry


class TrancheE2KernelTests(unittest.TestCase):
    def test_execution_plan_contains_only_real_stage_nodes(self) -> None:
        invocation = HostInvocation(prompt="Build a product report")
        manifest = InputIngestor().ingest(invocation, "run_test")
        contract = ProductContractCompiler().compile(invocation, manifest)

        dag = PlannerEnsemble().create_execution_plan("run_test", contract)

        self.assertEqual(
            [node.id for node in dag.nodes],
            [
                "T-AGGREGATE",
                "T-GAP-ANALYSIS",
                "T-SYNTHESIS",
                "T-CHAPTER-002",
                "T-CHAPTER-003",
                "T-ARTIFACT-BUILD",
                "T-QUALITY",
            ],
        )

    def test_plan_candidate_scores_change_with_real_contract_coverage(self) -> None:
        invocation = HostInvocation(prompt="Build a product report")
        manifest = InputIngestor().ingest(invocation, "run_test")
        contract = ProductContractCompiler().compile(invocation, manifest)
        planner = PlannerEnsemble()
        dag = planner.create_execution_plan("run_test", contract)

        covered = planner.create_candidate_plans(contract, dag)
        uncovered = planner.create_candidate_plans(
            contract.model_copy(update={"primary_artifacts": []}), dag
        )

        covered_by_role = {candidate.role: candidate.score for candidate in covered}
        uncovered_by_role = {candidate.role: candidate.score for candidate in uncovered}
        self.assertGreater(
            covered_by_role["strategic_planner"],
            uncovered_by_role["strategic_planner"],
        )

    def test_deterministic_adapter_never_echo_completes_unimplemented_work(self) -> None:
        descriptor = ProviderDescriptor(
            id="deterministic.tools",
            kind=ProviderKind.DETERMINISTIC_TOOL,
            enabled=True,
            capabilities={"artifact_build": 1.0},
            cost_tier=CostTier.FREE,
            health=ProviderHealth(
                status=ProviderStatus.HEALTHY,
                reliability_score=1.0,
            ),
        )
        task = TaskNode(
            id="T-NOT-IMPLEMENTED",
            run_id="run_test",
            title="Invent strategy",
            task_type=TaskType.PLANNING,
            required_capabilities={"strategic_reasoning": 0.8},
        )

        result = DeterministicToolsAdapter(descriptor).execute(
            ProviderTask(task=task, prompt="Plan", dry_run=True)
        )

        self.assertEqual(result.status, TaskStatus.SKIPPED)
        self.assertIn("no registered deterministic stage worker", result.warnings[0].lower())
        self.assertNotIn("completed by local deterministic tools", str(result.output).lower())

    def test_unavailable_strategic_capability_reaches_reshape_or_pause(self) -> None:
        task = TaskNode(
            id="T-STRATEGY",
            run_id="run_test",
            title="Strategic work",
            task_type=TaskType.PLANNING,
            required_capabilities={"strategic_reasoning": 0.8},
        )

        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "OLLAMA_BASE_URL": ""},
            clear=False,
        ):
            decision = AdaptiveRouter(CapabilityRegistry.from_environment()).route(task)

        self.assertIn(decision.action, {RoutingAction.RESHAPE, RoutingAction.PAUSE})
        self.assertIsNone(decision.provider_id)

    def test_default_local_run_contains_real_stage_outputs_and_no_echo_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Source\nA real stage must inspect this source passage.")

            result = Orchestrator(root / "runs").run(
                HostInvocation(
                    prompt="Build a serious report",
                    attachments=[{"uri": str(source)}],
                    cwd=str(root),
                )
            )
            run_dir = Path(result.artifact_dir)
            report = (run_dir / "final_report.md").read_text().lower()

            self.assertNotIn("completed by local deterministic tools", report)
            self.assertIn("source passage", report)
        self.assertEqual(len(result.manifest.routing_decisions), 7)


if __name__ == "__main__":
    unittest.main()
