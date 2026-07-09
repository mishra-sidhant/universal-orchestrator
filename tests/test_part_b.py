import tempfile
import unittest
from json import loads
from pathlib import Path

from universal_orchestrator.budget import BudgetController, COST_ORDER
from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.evidence import EvidenceAuditor
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    BudgetProfile,
    CostTier,
    ExecutionResult,
    HostInvocation,
    InputAttachment,
    ProductPackage,
    RunState,
    TaskStatus,
    UserOptions,
)
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.routing import AdaptiveRouter, CapabilityRegistry
from universal_orchestrator.runtime import RuntimeStore


class PartBGapTests(unittest.TestCase):
    def test_budget_controller_caps_task_cost_tiers(self) -> None:
        invocation = HostInvocation(
            prompt="Plan this cheaply",
            user_options=UserOptions(budget_profile=BudgetProfile.CHEAP),
        )
        manifest = InputIngestor().ingest(invocation, "run_test")
        cards = ContextIntelligence().build_cards(manifest)
        contract = ProductContractCompiler().compile(invocation, manifest)
        dag = PlannerEnsemble().create_execution_plan("run_test", contract)
        packs = ContextIntelligence().compile_packs_for_tasks([node.id for node in dag.nodes], cards)

        adjusted, report = BudgetController().apply(invocation, dag, packs)

        self.assertEqual(report.effective_max_cost_tier, CostTier.CHEAP)
        self.assertEqual(len(report.task_budgets), len(dag.nodes))
        self.assertTrue(all(COST_ORDER[node.max_cost_tier] <= COST_ORDER[CostTier.CHEAP] for node in adjusted.nodes))
        self.assertTrue(any(budget.original_max_cost_tier != budget.enforced_max_cost_tier for budget in report.task_budgets))

    def test_pipeline_writes_budget_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Product\nBuild the kernel spine.")
            result = Orchestrator(root / "runs").run(
                HostInvocation(
                    prompt="Build a serious implementation report",
                    attachments=[InputAttachment(uri=str(source))],
                    cwd=str(root),
                )
            )

            run_dir = Path(result.artifact_dir)
            self.assertTrue((run_dir / "budget_report.json").exists())

    def test_router_returns_provider_telemetry(self) -> None:
        invocation = HostInvocation(prompt="Route this work")
        manifest = InputIngestor().ingest(invocation, "run_test")
        contract = ProductContractCompiler().compile(invocation, manifest)
        dag = PlannerEnsemble().create_execution_plan("run_test", contract)

        decisions, telemetry = AdaptiveRouter(CapabilityRegistry.from_environment()).route_all_with_telemetry(
            "run_test",
            dag.topological_order(),
        )

        self.assertEqual(len(decisions), len(dag.nodes))
        self.assertEqual(telemetry.provider_count, len(CapabilityRegistry.from_environment().providers))
        self.assertEqual(len(telemetry.task_telemetry), len(dag.nodes))
        self.assertTrue(any(metric.provider_id == "deterministic.tools" for metric in telemetry.task_telemetry[0].metrics))

    def test_pipeline_writes_routing_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Product\nBuild the kernel spine.")
            result = Orchestrator(root / "runs").run(
                HostInvocation(
                    prompt="Build a serious implementation report",
                    attachments=[InputAttachment(uri=str(source))],
                    cwd=str(root),
                )
            )

            run_dir = Path(result.artifact_dir)
            self.assertTrue((run_dir / "routing_telemetry.json").exists())

    def test_delta_plan_reuses_unchanged_cached_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Product\nBuild the kernel spine.")
            orchestrator = Orchestrator(root / "runs")
            first = orchestrator.run(
                HostInvocation(
                    prompt="Build a serious implementation report",
                    attachments=[InputAttachment(uri=str(source))],
                    cwd=str(root),
                )
            )
            second = orchestrator.run(
                HostInvocation(
                    prompt="Build a serious implementation report",
                    attachments=[InputAttachment(uri=str(source))],
                    cwd=str(root),
                )
            )

            first_delta = loads((Path(first.artifact_dir) / "delta_execution_plan.json").read_text())
            second_delta = loads((Path(second.artifact_dir) / "delta_execution_plan.json").read_text())
            second_schedule = loads((Path(second.artifact_dir) / "schedule_report.json").read_text())

        self.assertEqual(first_delta["previous_run_id"], None)
        self.assertEqual(second_delta["previous_run_id"], first.run_id)
        self.assertFalse(second_delta["input_hash_changed"])
        self.assertTrue(second_delta["reusable_task_ids"])
        self.assertTrue(second_schedule["cache_hits"])

    def test_runtime_accepts_cancellation_for_non_terminal_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RuntimeStore(Path(tmp) / "runtime.sqlite3")
            store.transition("run_live", RunState.EXECUTING)

            result = store.request_cancel("run_live", "stop requested")
            snapshot = store.resumable_snapshot("run_live")

        self.assertTrue(result["accepted"])
        self.assertEqual(snapshot["latest_state"], RunState.CANCELLED)
        self.assertTrue(snapshot["cancel"]["requested"])

    def test_pipeline_writes_trace_and_debug_bundle_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Product\nBuild the kernel spine.")
            result = Orchestrator(root / "runs").run(
                HostInvocation(
                    prompt="Build a serious implementation report",
                    attachments=[InputAttachment(uri=str(source))],
                    cwd=str(root),
                )
            )

            run_dir = Path(result.artifact_dir)
            trace = loads((run_dir / "trace_report.json").read_text())
            debug = loads((run_dir / "debug_bundle_manifest.json").read_text())

        span_names = {span["name"] for span in trace["spans"]}
        self.assertIn("ingestion", span_names)
        self.assertIn("execution", span_names)
        self.assertIn("final_assembly", span_names)
        self.assertIn("trace_report.json", debug["trace_names"])
        self.assertFalse(debug["safe_to_share"])

    def test_evidence_auditor_detects_unsupported_output(self) -> None:
        audit = EvidenceAuditor().audit(
            ProductPackage(run_id="run_test", final_markdown="# Final\nNo context.", summary="summary"),
            cards=[],
            provenance=[],
            results=[
                ExecutionResult(
                    task_id="T-001",
                    provider_id="deterministic.tools",
                    status=TaskStatus.COMPLETED,
                    output={"worker_output": {"summary": "done", "evidence_refs": []}},
                )
            ],
        )

        self.assertFalse(audit.passed)
        self.assertIn("T-001", audit.unsupported_task_ids)

    def test_pipeline_writes_passing_evidence_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Product\nBuild the kernel spine.")
            result = Orchestrator(root / "runs").run(
                HostInvocation(
                    prompt="Build a serious implementation report",
                    attachments=[InputAttachment(uri=str(source))],
                    cwd=str(root),
                )
            )

            run_dir = Path(result.artifact_dir)
            audit = loads((run_dir / "evidence_audit.json").read_text())
            quality = loads((run_dir / "quality_report.json").read_text())

        self.assertTrue(audit["passed"])
        self.assertTrue(audit["cited_source_ids"])
        self.assertGreaterEqual(quality["scores"]["citation_support"], 85)


if __name__ == "__main__":
    unittest.main()
