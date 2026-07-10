import tempfile
import unittest
from pathlib import Path

from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.evidence import EvidenceAuditor
from universal_orchestrator.execution import DeterministicExecutor
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    CostTier,
    ExecutionResult,
    HostInvocation,
    ProviderDescriptor,
    ProviderHealth,
    ProviderKind,
    ProviderResult,
    ProviderStatus,
    QualityScore,
    RoutingAction,
    RoutingDecision,
    TaskNode,
    TaskStatus,
    TaskType,
)
from universal_orchestrator.providers.base import ProviderAdapter, ProviderAdapterRegistry
from universal_orchestrator.workers import StructuredWorkerOutputBuilder


class ContextRecordingAdapter(ProviderAdapter):
    def __init__(self) -> None:
        super().__init__(
            ProviderDescriptor(
                id="context.recorder",
                kind=ProviderKind.DETERMINISTIC_TOOL,
                enabled=True,
                capabilities={"summarization": 1.0},
                cost_tier=CostTier.FREE,
                health=ProviderHealth(
                    status=ProviderStatus.HEALTHY,
                    reliability_score=1.0,
                ),
            )
        )
        self.consumed_refs: list[str] = []

    def execute(self, task) -> ProviderResult:
        self.consumed_refs = list(task.context.get("consumed_chunk_refs", []))
        return ProviderResult(
            provider_id=self.id,
            status=TaskStatus.COMPLETED,
            output={"summary": "grounded summary"},
        )


class TrancheE1EvidenceTests(unittest.TestCase):
    def test_empty_task_pack_does_not_fallback_to_global_chunks(self) -> None:
        task = TaskNode(
            id="T-EMPTY",
            run_id="run_test",
            title="Empty pack",
            task_type=TaskType.SUMMARIZATION,
        )
        decision = RoutingDecision(
            task_id=task.id,
            action=RoutingAction.ROUTE,
            provider_id="deterministic.tools",
            reason="test",
        )

        output = StructuredWorkerOutputBuilder().build(
            task,
            decision,
            None,
            {
                "chunk_refs": ["chunk_global"],
                "chunk_refs_by_task": {task.id: []},
            },
            TaskStatus.COMPLETED,
        )

        self.assertEqual(output["evidence_refs"], [])

    def test_executor_passes_consumed_task_refs_to_adapter_and_output(self) -> None:
        adapter = ContextRecordingAdapter()
        task = TaskNode(
            id="T-CONTEXT",
            run_id="run_test",
            title="Consume context",
            task_type=TaskType.SUMMARIZATION,
        )
        decision = RoutingDecision(
            task_id=task.id,
            action=RoutingAction.ROUTE,
            provider_id=adapter.id,
            reason="test",
        )
        executor = DeterministicExecutor(
            adapters=ProviderAdapterRegistry([adapter]),
            context={
                "chunk_refs": ["chunk_global"],
                "chunk_refs_by_task": {task.id: ["chunk_consumed"]},
            },
        )

        result = executor.execute([task], [decision])[0]

        self.assertEqual(adapter.consumed_refs, ["chunk_consumed"])
        self.assertEqual(result.output["worker_output"]["evidence_refs"], ["chunk_consumed"])

    def test_auditor_rejects_real_but_unconsumed_chunk_reference(self) -> None:
        cards, chunks, provenance = self._source_context()
        consumed = chunks[0].id
        fabricated = chunks[1].id
        result = self._result("T-001", [consumed, fabricated])

        audit = EvidenceAuditor().audit(
            None,
            cards,
            provenance,
            [result],
            chunks,
            run_id="run_test",
            consumed_chunk_refs_by_task={"T-001": [consumed]},
        )

        self.assertFalse(audit.passed)
        self.assertEqual(audit.unconsumed_evidence_refs, [fabricated])
        self.assertFalse(audit.claims[0].resolved)

    def test_missing_refs_identifies_exact_unsupported_task(self) -> None:
        cards, chunks, provenance = self._source_context()
        supported = self._result("T-SUPPORTED", [chunks[0].id])
        unsupported = self._result("T-UNSUPPORTED", [])

        audit = EvidenceAuditor().audit(
            None,
            cards,
            provenance,
            [supported, unsupported],
            chunks,
            run_id="run_test",
            consumed_chunk_refs_by_task={"T-SUPPORTED": [chunks[0].id], "T-UNSUPPORTED": []},
        )
        claim_support = next(
            finding for finding in audit.findings if finding.kind == "claim_support"
        )

        self.assertEqual(audit.unsupported_task_ids, ["T-UNSUPPORTED"])
        self.assertEqual(claim_support.metadata["unsupported_task_ids"], ["T-UNSUPPORTED"])
        self.assertEqual(claim_support.metadata["supported_claims"], 1)
        self.assertEqual(claim_support.metadata["claim_count"], 2)

    def test_quality_score_schema_has_no_synthetic_check_names(self) -> None:
        fields = set(QualityScore.model_fields)

        self.assertNotIn("factuality", fields)
        self.assertNotIn("style_quality", fields)
        self.assertNotIn("cost_efficiency", fields)
        self.assertIn("parse_confidence", fields)
        self.assertNotIn("artifact_render_check", fields)
        self.assertIn("artifact_presence", fields)
        self.assertIn("routing_efficiency", fields)

    def _source_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text(" ".join(f"evidence-{index}" for index in range(400)))
            manifest = InputIngestor().ingest(
                HostInvocation(
                    prompt="Analyze evidence",
                    attachments=[{"uri": str(source)}],
                    cwd=str(root),
                ),
                "run_test",
            )
            context = ContextIntelligence()
            cards = context.build_cards(manifest)
            chunks = [
                chunk
                for chunk in context.chunk_manifest(manifest, max_tokens=40)
                if chunk.input_id != "input_prompt"
            ]
            provenance = context.provenance(cards, chunks)
            return cards, chunks, provenance

    def _result(self, task_id: str, refs: list[str]) -> ExecutionResult:
        return ExecutionResult(
            task_id=task_id,
            provider_id="deterministic.tools",
            status=TaskStatus.COMPLETED,
            output={
                "worker_output": {
                    "summary": f"Claim for {task_id}",
                    "evidence_refs": refs,
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
