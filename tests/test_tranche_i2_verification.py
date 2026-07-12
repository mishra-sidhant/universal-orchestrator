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
