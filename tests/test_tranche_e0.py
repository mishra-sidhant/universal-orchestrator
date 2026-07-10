import tempfile
import unittest
import zipfile
from pathlib import Path

from pydantic import ValidationError

from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.evidence import EvidenceAuditor
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    ExecutionResult,
    HostInvocation,
    RunState,
    TaskStatus,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.product import FinalProductOwner
from universal_orchestrator.quality import QualityGateEngine
from universal_orchestrator.routing import AdaptiveRouter, CapabilityRegistry
from universal_orchestrator.scheduler import DAGScheduler
from universal_orchestrator.validators import ValidatorRegistry


class FailFirstScheduler(DAGScheduler):
    def __init__(self, events: list[str] | None = None) -> None:
        super().__init__()
        self.calls = 0
        self.events = events

    def execute(self, *args, **kwargs):
        self.calls += 1
        if self.events is not None:
            self.events.append(f"scheduler:{self.calls}")
        results, report = super().execute(*args, **kwargs)
        if self.calls == 1:
            results[0] = results[0].model_copy(
                update={"status": TaskStatus.FAILED, "warnings": ["forced primary failure"]}
            )
            report = report.model_copy(update={"failed_tasks": [results[0].task_id]})
        return results, report


class RecordingEvidenceAuditor(EvidenceAuditor):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def audit(self, *args, **kwargs):
        self.events.append("evidence")
        return super().audit(*args, **kwargs)


class RecordingProductOwner(FinalProductOwner):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def assemble(self, *args, **kwargs):
        self.events.append("product")
        return super().assemble(*args, **kwargs)


class TrancheE0RegressionTests(unittest.TestCase):
    def test_post_repair_quality_rates_use_original_and_repair_task_union(self) -> None:
        invocation = HostInvocation(prompt="Build a report")
        manifest = InputIngestor().ingest(invocation, "run_test")
        contract = ProductContractCompiler().compile(invocation, manifest)
        dag = PlannerEnsemble().create_execution_plan("run_test", contract)
        decisions = AdaptiveRouter(CapabilityRegistry.from_environment()).route_all(
            dag.topological_order()
        )
        primary_results = [
            ExecutionResult(
                task_id=node.id,
                provider_id="deterministic.tools",
                status=TaskStatus.FAILED if index == 0 else TaskStatus.COMPLETED,
                output={"worker_output": {"summary": "result", "evidence_refs": []}},
            )
            for index, node in enumerate(dag.nodes)
        ]
        repair_results = [
            ExecutionResult(
                task_id=f"T-REPAIR-{index:03d}",
                provider_id="deterministic.tools",
                status=TaskStatus.COMPLETED,
                output={"worker_output": {"summary": "repair", "evidence_refs": []}},
            )
            for index in range(1, 4)
        ]

        try:
            quality = QualityGateEngine().evaluate(
                manifest,
                contract,
                dag,
                decisions,
                [*primary_results, *repair_results],
                [Path(__file__)],
            )
        except ValidationError as exc:
            self.fail(f"post-repair quality evaluation crashed: {exc}")

        self.assertLessEqual(quality.scores.continuity, 100)
        self.assertLessEqual(quality.scores.completeness, 100)

    def test_failed_execution_finding_uses_failure_description(self) -> None:
        failed = ExecutionResult(
            task_id="T-FAILED",
            provider_id="deterministic.tools",
            status=TaskStatus.FAILED,
            output={},
        )

        finding = ValidatorRegistry()._execution_findings([failed])[0]

        self.assertFalse(finding.passed)
        self.assertNotEqual(finding.message, "No execution result failed.")
        self.assertIn("T-FAILED", finding.message)
        self.assertNotEqual(finding.pass_message, finding.fail_message)

    def test_pipeline_repair_uses_scheduler_audits_before_repair_and_assembles_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events: list[str] = []
            orchestrator = Orchestrator(Path(tmp) / "runs")
            orchestrator.scheduler = FailFirstScheduler(events)
            orchestrator.evidence = RecordingEvidenceAuditor(events)
            orchestrator.product_owner = RecordingProductOwner(events)

            result = orchestrator.run(HostInvocation(prompt="Build a repairable report"))

            self.assertIn(result.state, {RunState.DELIVERED, RunState.NEEDS_ATTENTION})
            self.assertGreaterEqual(events.count("scheduler:2"), 1)
            self.assertLess(events.index("evidence"), events.index("scheduler:2"))
            self.assertEqual(events.count("product"), 1)

    def test_secret_in_prompt_never_reaches_files_or_delivery_zip(self) -> None:
        secret = "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
        with tempfile.TemporaryDirectory() as tmp:
            result = Orchestrator(Path(tmp) / "runs").run(
                HostInvocation(prompt=f"Build a report using token {secret}")
            )
            run_dir = Path(result.artifact_dir)

            for path in run_dir.iterdir():
                if path.is_file() and path.suffix != ".zip":
                    self.assertNotIn(secret.encode(), path.read_bytes(), path.name)
            with zipfile.ZipFile(run_dir / "delivery_bundle.zip") as archive:
                for member in archive.namelist():
                    self.assertNotIn(secret.encode(), archive.read(member), member)

    def test_quality_failed_run_needs_attention_without_delivery_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = Orchestrator(Path(tmp) / "runs")
            orchestrator.scheduler = FailFirstScheduler()

            result = orchestrator.run(HostInvocation(prompt="Build a report with forced failure"))
            run_dir = Path(result.artifact_dir)

            self.assertEqual(result.state, RunState.NEEDS_ATTENTION)
            self.assertFalse(result.quality.passed)
            self.assertFalse((run_dir / "delivery_receipt.json").exists())
            self.assertIsNone(result.manifest.delivery_receipt_path)


if __name__ == "__main__":
    unittest.main()
