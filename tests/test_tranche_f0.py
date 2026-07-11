from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.evidence import EvidenceAuditor
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    ContextCard,
    ContextChunk,
    ExecutionResult,
    HostInvocation,
    ProvenanceRecord,
    QualityGateResult,
    QualityScore,
    RoutingAction,
    RoutingDecision,
    TaskStatus,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.quality import QualityGateEngine


class TrancheF0HonestyTests(unittest.TestCase):
    def test_citation_support_is_ratio_for_one_unsupported_claim(self) -> None:
        chunk = ContextChunk(
            id="chunk_supported",
            input_id="input_source",
            ordinal=0,
            text="Grounded evidence passage.",
            token_estimate=4,
            content_hash="sha256:source",
        )
        card = ContextCard(
            id="card_source",
            input_id=chunk.input_id,
            card_type="source",
            title="Source",
            summary="Grounded evidence passage.",
        )
        provenance = ProvenanceRecord(
            source_id=chunk.input_id,
            card_id=card.id,
            chunk_ids=[chunk.id],
            source_name="Source",
            trust_level="source",
        )
        results = [
            self._claim_result("T-SUPPORTED", [chunk.id]),
            self._claim_result("T-UNSUPPORTED", []),
        ]
        audit = EvidenceAuditor().audit(
            None,
            [card],
            [provenance],
            results,
            [chunk],
            run_id="run_ratio",
            consumed_chunk_refs_by_task={"T-SUPPORTED": [chunk.id], "T-UNSUPPORTED": []},
        )
        quality = self._quality()

        updated = EvidenceAuditor().apply_to_quality(quality, audit, source_required=False)

        self.assertEqual(updated.scores.citation_support, 50)
        self.assertEqual(audit.unsupported_task_ids, ["T-UNSUPPORTED"])

    def test_quality_engine_does_not_infer_citation_score_from_contract_keywords(self) -> None:
        invocation = HostInvocation(prompt="Plan a local task")
        manifest = InputIngestor().ingest(invocation, "run_provisional")
        contract = ProductContractCompiler().compile(invocation, manifest)
        dag = PlannerEnsemble().create_execution_plan("run_provisional", contract)
        decisions = [
            RoutingDecision(
                task_id=node.id,
                action=RoutingAction.ROUTE,
                provider_id="deterministic.tools",
                reason="test",
            )
            for node in dag.nodes
        ]
        results = [
            ExecutionResult(
                task_id=node.id,
                provider_id="deterministic.tools",
                status=TaskStatus.COMPLETED,
                output={"worker_output": {"summary": "completed", "evidence_required": False}},
            )
            for node in dag.nodes
        ]

        quality = QualityGateEngine().evaluate(
            manifest,
            contract,
            dag,
            decisions,
            results,
            [Path(__file__)],
        )

        self.assertEqual(quality.scores.citation_support, 0)

    def test_delivered_audit_reports_final_citations_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("The source-backed synthesis has a real citation.")
            result = Orchestrator(root / "runs").run(
                HostInvocation(
                    prompt="Build a serious report from this source",
                    attachments=[{"uri": str(source)}],
                )
            )
            run_dir = Path(result.artifact_dir)
            audit = json.loads((run_dir / "evidence_audit.json").read_text())
            report = (run_dir / "final_report.md").read_text()

        final_citations = next(item for item in audit["findings"] if item["kind"] == "final_citations")
        self.assertTrue(final_citations["passed"])
        self.assertIn("## Sources", report)
        self.assertTrue(audit["passed"])

    def _claim_result(self, task_id: str, refs: list[str]) -> ExecutionResult:
        return ExecutionResult(
            task_id=task_id,
            provider_id="deterministic.tools",
            status=TaskStatus.COMPLETED,
            output={
                "worker_output": {
                    "summary": f"Claim for {task_id}",
                    "evidence_refs": refs,
                    "evidence_required": True,
                }
            },
        )

    def _quality(self) -> QualityGateResult:
        return QualityGateResult(
            passed=True,
            scores=QualityScore(
                completeness=100,
                parse_confidence=100,
                citation_support=0,
                continuity=100,
                routing_efficiency=100,
                artifact_presence="pass",
                code_validation="not_applicable",
            ),
        )


if __name__ == "__main__":
    unittest.main()
