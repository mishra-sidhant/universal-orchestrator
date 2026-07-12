from __future__ import annotations

import re
from typing import Protocol

from universal_orchestrator.models import (
    ClaimVerification,
    ClaimVerificationStatus,
    ContextChunk,
)


class ClaimVerifier(Protocol):
    def verify(
        self,
        claim_text: str,
        evidence_refs: list[str],
        chunks: list[ContextChunk],
    ) -> ClaimVerification:
        """Verify a claim without treating retrieval similarity as proof."""


class StructuralClaimVerifier:
    """Reference and lexical-floor verifier; semantic entailment remains unknown."""

    def verify(
        self,
        claim_text: str,
        evidence_refs: list[str],
        chunks: list[ContextChunk],
    ) -> ClaimVerification:
        chunks_by_id = {chunk.id: chunk for chunk in chunks}
        resolved = [chunks_by_id[ref] for ref in evidence_refs if ref in chunks_by_id]
        if not evidence_refs or len(resolved) != len(evidence_refs):
            return ClaimVerification(
                claim_text=claim_text,
                status=ClaimVerificationStatus.INSUFFICIENT,
                evidence_refs=evidence_refs,
                method="structural_reference_check",
                warning="One or more evidence references did not resolve to delivered chunks.",
            )
        claim_terms = _terms(claim_text)
        evidence_terms = set().union(*(_terms(chunk.text) for chunk in resolved))
        overlap = len(claim_terms.intersection(evidence_terms)) / max(1, len(claim_terms))
        warning = (
            "Lexical overlap is below the weak diagnostic floor; this is not an entailment judgment."
            if overlap < 0.1
            else "Semantic entailment was not evaluated by this verifier."
        )
        return ClaimVerification(
            claim_text=claim_text,
            status=ClaimVerificationStatus.UNKNOWN,
            evidence_refs=evidence_refs,
            lexical_overlap=overlap,
            method="structural_reference_check",
            warning=warning,
        )


def _terms(text: str) -> set[str]:
    return {term for term in re.findall(r"[A-Za-z0-9_]+", text.casefold()) if len(term) > 2}
