from __future__ import annotations

from hashlib import sha256
import unittest

from universal_orchestrator.models import (
    ClaimVerificationStatus,
    ContextChunk,
    CostTier,
    ProviderDescriptor,
    ProviderKind,
    ProviderResult,
    ProviderStatus,
    ProviderHealth,
    TaskStatus,
)
from universal_orchestrator.verification import (
    ProviderClaimVerifier,
    UnknownClaimVerifier,
)


class _FixtureAdapter:
    descriptor = ProviderDescriptor(
        id="fixture.semantic",
        kind=ProviderKind.HOSTED_MODEL,
        model_id="fixture-model",
        cost_tier=CostTier.CHEAP,
        capabilities={"structured_output": 1.0},
        health=ProviderHealth(status=ProviderStatus.HEALTHY),
    )

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def execute(self, task):
        del task
        self.calls += 1
        return ProviderResult(
            provider_id=self.descriptor.id,
            status=TaskStatus.COMPLETED,
            output={"summary": self.response},
        )


class SemanticVerificationTests(unittest.TestCase):
    def _chunk(self) -> ContextChunk:
        text = "The kernel is bounded."
        return ContextChunk(
            id="chunk-source",
            input_id="input-source",
            ordinal=0,
            text=text,
            token_estimate=4,
            content_hash=sha256(text.encode()).hexdigest(),
        )

    def test_provider_verdict_is_structured_and_cached(self) -> None:
        adapter = _FixtureAdapter(
            '{"verdict":"supported","rationale":"The evidence states the claim.","confidence":0.91}'
        )
        verifier = ProviderClaimVerifier(adapter, "run-semantic")

        first = verifier.verify("The kernel is bounded.", ["chunk-source"], [self._chunk()])
        second = verifier.verify("The kernel is bounded.", ["chunk-source"], [self._chunk()])

        self.assertEqual(first.status, ClaimVerificationStatus.SUPPORTED)
        self.assertEqual(first.confidence, 0.91)
        self.assertEqual(first.rationale, "The evidence states the claim.")
        self.assertEqual(second, first)
        self.assertEqual(adapter.calls, 1)

    def test_malformed_provider_verdict_is_unknown(self) -> None:
        verifier = ProviderClaimVerifier(_FixtureAdapter("not-json"), "run-semantic")

        result = verifier.verify("The kernel is bounded.", ["chunk-source"], [self._chunk()])

        self.assertEqual(result.status, ClaimVerificationStatus.UNKNOWN)
        self.assertIn("valid verdict", result.warning or "")

    def test_unavailable_required_verifier_never_claims_support(self) -> None:
        result = UnknownClaimVerifier().verify(
            "The kernel is bounded.", ["chunk-source"], [self._chunk()]
        )

        self.assertEqual(result.status, ClaimVerificationStatus.UNKNOWN)
        self.assertIn("no authorized verifier", result.warning or "")


if __name__ == "__main__":
    unittest.main()
