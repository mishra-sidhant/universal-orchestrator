from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    ExecutionResult,
    HostInvocation,
    RoutingAction,
    RoutingDecision,
    TaskDAG,
    TaskNode,
    TaskStatus,
    TaskType,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.product import FinalProductOwner
from universal_orchestrator.cache import ExactMatchCache
from universal_orchestrator.scheduler import DAGScheduler
from universal_orchestrator.validators import ValidatorRegistry


class TrancheO4ValidatorPanelTests(unittest.TestCase):
    def test_scheduler_cache_fingerprint_includes_output_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler = DAGScheduler(ExactMatchCache(Path(tmp)))
            task = TaskNode(
                id="T-SYNTHESIS",
                run_id="R",
                title="Synthesis",
                task_type=TaskType.FINAL_SYNTHESIS,
                chapter_id="chapter-1",
                chapter_title="Executive Summary",
                objective="Answer the request.",
            )

            original_key = scheduler.cache_key_for_task(task)
            changed_key = scheduler.cache_key_for_task(
                task.model_copy(update={"objective": "Answer the revised request."})
            )

        self.assertNotEqual(original_key, changed_key)

    def test_validator_panel_rejects_missing_manuscript_contract(self) -> None:
        invocation = HostInvocation(prompt="Produce a report")
        manifest = InputIngestor().ingest(invocation, "R")
        contract = ProductContractCompiler().compile(invocation, manifest)
        task = TaskNode(
            id="T-SYNTHESIS",
            run_id="R",
            title="Synthesis",
            task_type=TaskType.FINAL_SYNTHESIS,
            chapter_id="chapter-1",
            chapter_title="Executive Summary",
            objective="Answer the request.",
        )
        dag = TaskDAG(run_id="R", nodes=[task])
        plan = PlannerEnsemble().create_product_plan("R", contract, [task.id])
        decisions = [
            RoutingDecision(
                task_id=task.id,
                action=RoutingAction.ROUTE,
                provider_id="deterministic.tools",
                reason="fixture",
            )
        ]
        result = ExecutionResult(
            task_id=task.id,
            provider_id="deterministic.tools",
            status=TaskStatus.COMPLETED,
            output={"worker_output": {"summary": "Summary without manuscript."}},
        )

        findings = ValidatorRegistry().evaluate(
            manifest,
            contract,
            dag,
            decisions,
            [result],
            [Path(__file__)],
            product_plan=plan,
        )

        manuscript_findings = [item for item in findings if item.validator == "manuscript"]
        self.assertTrue(manuscript_findings)
        self.assertFalse(all(item.passed for item in manuscript_findings))
        self.assertTrue(any(item.severity == "high" for item in manuscript_findings))

    def test_pipeline_persists_validator_panel_with_failed_identity_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = Orchestrator(Path(tmp) / "runs").run(
                HostInvocation(prompt="Produce a grounded report")
            )
            panel = json.loads(
                (Path(result.artifact_dir) / "validator_panel.json").read_text()
            )

        self.assertEqual(panel["schema_version"], "1.0")
        self.assertIn("findings", panel)
        self.assertIn("failed_validators", panel)
        self.assertIn("manuscript", {finding["validator"] for finding in panel["findings"]})
        self.assertTrue(panel["passed"])

    def test_product_owner_rejects_missing_manuscript_fragment(self) -> None:
        task = TaskNode(
            id="T-SYNTHESIS",
            run_id="R",
            title="Synthesis",
            task_type=TaskType.FINAL_SYNTHESIS,
            chapter_id="chapter-1",
            chapter_title="Executive Summary",
            objective="Answer the request.",
        )
        result = ExecutionResult(
            task_id=task.id,
            provider_id="deterministic.tools",
            status=TaskStatus.COMPLETED,
            output={"worker_output": {"summary": "Summary without manuscript."}},
        )
        quality = SimpleNamespace(
            warnings=[],
            violations=[],
            scores=SimpleNamespace(
                completeness=90,
                parse_confidence=90,
                citation_support=90,
                continuity=90,
                routing_efficiency=90,
                artifact_presence="pass",
                code_validation="not_applicable",
            ),
        )

        package = FinalProductOwner().assemble(
            SimpleNamespace(run_id="R", inputs=[], parsed_count=0),
            SimpleNamespace(
                run_type="research_report",
                requested_output="Produce a report",
                primary_artifacts=["final_report"],
                quality_bar="serious",
            ),
            [],
            SimpleNamespace(nodes=[task]),
            [],
            [result],
            quality,
        )

        self.assertTrue(any("missing manuscript" in item.lower() for item in package.rejected_fragments))
        self.assertIn("Rejected Fragments", package.final_markdown)


if __name__ == "__main__":
    unittest.main()
