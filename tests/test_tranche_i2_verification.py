from __future__ import annotations

import unittest

from universal_orchestrator.models import ClaimVerificationStatus, ContextChunk
from universal_orchestrator.verification import StructuralClaimVerifier


def chunk(chunk_id: str, text: str) -> ContextChunk:
    return ContextChunk(
        id=chunk_id,
        input_id="input",
        ordinal=0,
        text=text,
        token_estimate=5,
        content_hash=chunk_id,
        metadata={},
    )


class ClaimVerificationTests(unittest.TestCase):
    def test_configured_contradiction_blocks_evidence_audit(self) -> None:
        from universal_orchestrator.evidence import EvidenceAuditor
        from universal_orchestrator.models import (
            ClaimVerification,
            ContextCard,
            ExecutionResult,
            ProvenanceRecord,
            TaskStatus,
            utc_now,
        )

        class ContradictingVerifier:
            def verify(self, claim_text: str, evidence_refs: list[str], chunks: list[ContextChunk]) -> ClaimVerification:
                del chunks
                return ClaimVerification(
                    claim_text=claim_text,
                    evidence_refs=evidence_refs,
                    status=ClaimVerificationStatus.CONTRADICTED,
                    method="fixture_contradiction",
                    warning="fixture",
                )

        source_card = ContextCard(
            id="card-1",
            input_id="input-1",
            card_type="source",
            title="Source",
            summary="Source",
        )
        source = ProvenanceRecord(
            source_id="source-1",
            card_id="card-1",
            chunk_ids=["real"],
            trust_level="source",
        )
        result = ExecutionResult(
            task_id="T-SYNTHESIS",
            provider_id="fixture",
            status=TaskStatus.COMPLETED,
            output={
                "worker_output": {
                    "summary": "The source says bounded execution.",
                    "evidence_refs": ["real"],
                    "evidence_required": True,
                }
            },
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        audit = EvidenceAuditor(ContradictingVerifier()).audit(
            None,
            [source_card],
            [source],
            [result],
            chunks=[chunk("real", "bounded execution")],
            consumed_chunk_refs_by_task={"T-SYNTHESIS": ["real"]},
        )

        self.assertFalse(audit.passed)
        self.assertEqual(audit.verification_blockers, ["T-SYNTHESIS"])
        self.assertEqual(
            audit.claims[0].verification.status,
            ClaimVerificationStatus.CONTRADICTED,
        )

    def test_fabricated_reference_is_insufficient(self) -> None:
        result = StructuralClaimVerifier().verify(
            "The source says bounded execution.", ["fabricated"], [chunk("real", "bounded execution")]
        )
        self.assertEqual(result.status, ClaimVerificationStatus.INSUFFICIENT)

    def test_valid_reference_is_not_mislabeled_as_entailment(self) -> None:
        result = StructuralClaimVerifier().verify(
            "The source says bounded execution.", ["real"], [chunk("real", "bounded execution")]
        )
        self.assertEqual(result.status, ClaimVerificationStatus.UNKNOWN)
        self.assertIn("entailment", result.warning or "")

    def test_weak_overlap_is_a_warning(self) -> None:
        result = StructuralClaimVerifier().verify(
            "Quantum gardening is guaranteed.", ["real"], [chunk("real", "bounded execution")]
        )
        self.assertEqual(result.status, ClaimVerificationStatus.UNKNOWN)
        self.assertIn("weak diagnostic floor", result.warning or "")


if __name__ == "__main__":
    unittest.main()
