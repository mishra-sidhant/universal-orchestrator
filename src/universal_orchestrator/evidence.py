from __future__ import annotations

from universal_orchestrator.models import (
    ContextCard,
    ContextChunk,
    EvidenceClaim,
    EvidenceAuditFinding,
    EvidenceAuditReport,
    ExecutionResult,
    ProductPackage,
    ProvenanceRecord,
    QualityGateResult,
    ClaimVerificationStatus,
    task_succeeded,
)
from universal_orchestrator.verification import ClaimVerifier, StructuralClaimVerifier


class EvidenceAuditor:
    def __init__(self, claim_verifier: ClaimVerifier | None = None) -> None:
        self.claim_verifier = claim_verifier or StructuralClaimVerifier()

    def audit(
        self,
        package: ProductPackage | None,
        cards: list[ContextCard],
        provenance: list[ProvenanceRecord],
        results: list[ExecutionResult],
        chunks: list[ContextChunk] | None = None,
        run_id: str | None = None,
        consumed_chunk_refs_by_task: dict[str, list[str]] | None = None,
    ) -> EvidenceAuditReport:
        evidence_refs = self._worker_evidence_refs(results)
        valid_chunk_ids = {chunk.id for chunk in chunks or []}
        invalid_evidence_refs = sorted(evidence_refs.difference(valid_chunk_ids))
        consumed = {
            task_id: set(refs)
            for task_id, refs in (consumed_chunk_refs_by_task or {}).items()
        }
        claims = self._claims(results, valid_chunk_ids, consumed, chunks or [])
        evidence_claims = [claim for claim in claims if claim.evidence_required]
        unsupported_task_ids = sorted({claim.task_id for claim in claims if not claim.resolved})
        verification_blockers = sorted(
            {
                claim.task_id
                for claim in claims
                if claim.evidence_required
                and claim.verification is not None
                and claim.verification.status == ClaimVerificationStatus.CONTRADICTED
            }
        )
        unconsumed_evidence_refs = sorted(
            {
                ref
                for claim in claims
                for ref in claim.evidence_refs
                if ref not in consumed.get(claim.task_id, set())
            }
        )
        supported_refs = {
            ref for claim in claims if claim.citation_eligible for ref in claim.evidence_refs
        }
        source_by_chunk = {
            chunk_id: record.source_id
            for record in provenance
            for chunk_id in record.chunk_ids
        }
        cited_source_ids = sorted(
            {source_by_chunk[ref] for ref in supported_refs if ref in source_by_chunk}
        )
        final_markdown = package.final_markdown if package is not None else ""
        final_citations_present = bool(package) and "## Sources" in final_markdown and all(
            f"[{ref}]" in final_markdown for ref in supported_refs
        )
        findings = [
            EvidenceAuditFinding(
                kind="source_inventory",
                passed=bool(cards),
                severity="high",
                message="Context cards are available to support the final package.",
                metadata={"card_count": len(cards)},
            ),
            EvidenceAuditFinding(
                kind="provenance",
                passed=bool(provenance),
                severity="high",
                message="Context provenance records connect cards to source chunks.",
                metadata={"provenance_count": len(provenance)},
            ),
            EvidenceAuditFinding(
                kind="reference_resolution",
                passed=(
                    bool(evidence_refs)
                    and not invalid_evidence_refs
                    and not unconsumed_evidence_refs
                ),
                severity="high",
                message="Worker evidence references resolve to chunks consumed by that task.",
                metadata={
                    "invalid_evidence_refs": invalid_evidence_refs,
                    "unconsumed_evidence_refs": unconsumed_evidence_refs,
                },
            ),
            EvidenceAuditFinding(
                kind="claim_support",
                passed=not unsupported_task_ids,
                severity="medium",
                message="Source-derived worker claims include resolvable evidence references.",
                metadata={
                    "unsupported_task_ids": unsupported_task_ids,
                    "supported_claims": len(
                        [claim for claim in evidence_claims if claim.resolved]
                    ),
                    "claim_count": len(evidence_claims),
                },
            ),
            EvidenceAuditFinding(
                kind="claim_verification",
                passed=not verification_blockers,
                severity="high" if verification_blockers else "medium",
                message=(
                    "Configured claim verification found no contradiction."
                    if not verification_blockers
                    else "Configured claim verification contradicted one or more claims."
                ),
                metadata={"verification_blockers": verification_blockers},
            ),
            EvidenceAuditFinding(
                kind="final_citations",
                passed=final_citations_present,
                severity="medium" if package else "info",
                message=(
                    "Final markdown includes resolvable inline citations and a Sources section."
                    if package
                    else "Final citation rendering is deferred until final assembly."
                ),
            ),
        ]
        passed = all(finding.passed for finding in findings if finding.severity in {"high", "critical"})
        passed = (
            passed
            and not unsupported_task_ids
            and not verification_blockers
            and (final_citations_present if package else True)
        )
        return EvidenceAuditReport(
            run_id=package.run_id if package else (run_id or "unknown"),
            passed=passed,
            source_count=len(cards),
            provenance_count=len(provenance),
            cited_source_ids=cited_source_ids,
            unsupported_task_ids=unsupported_task_ids,
            invalid_evidence_refs=invalid_evidence_refs,
            unconsumed_evidence_refs=unconsumed_evidence_refs,
            verification_blockers=verification_blockers,
            claims=claims,
            findings=findings,
        )

    def apply_to_quality(
        self,
        quality: QualityGateResult,
        audit: EvidenceAuditReport,
        source_required: bool,
    ) -> QualityGateResult:
        evidence_claims = [claim for claim in audit.claims if claim.evidence_required]
        claim_count = len(evidence_claims)
        supported_claims = len([claim for claim in evidence_claims if claim.citation_eligible])
        citation_score = round(100 * supported_claims / claim_count) if claim_count else 0
        if audit.passed:
            scores = quality.scores.model_copy(
                update={"citation_support": citation_score}
            )
            return quality.model_copy(update={"scores": scores})

        message = "Evidence audit did not find sufficient support for the final package."
        scores = quality.scores.model_copy(
            update={"citation_support": citation_score}
        )
        warnings = [*quality.warnings, message]
        violations = list(quality.violations)
        passed = quality.passed
        if source_required or evidence_claims:
            violations.append(message)
            passed = False
        return quality.model_copy(
            update={
                "passed": passed,
                "scores": scores,
                "warnings": warnings,
                "violations": violations,
            }
        )

    def _worker_evidence_refs(self, results: list[ExecutionResult]) -> set[str]:
        refs: set[str] = set()
        for result in results:
            worker_output = result.output.get("worker_output", {})
            if isinstance(worker_output, dict):
                refs.update(str(ref) for ref in worker_output.get("evidence_refs", []) if ref)
        return refs

    def _claims(
        self,
        results: list[ExecutionResult],
        valid_chunk_ids: set[str],
        consumed_chunk_refs_by_task: dict[str, set[str]],
        chunks: list[ContextChunk],
    ) -> list[EvidenceClaim]:
        claims: list[EvidenceClaim] = []
        for result in results:
            if not task_succeeded(result.status):
                continue
            worker_output = result.output.get("worker_output", {})
            if not isinstance(worker_output, dict):
                worker_output = {}
            evidence_required = bool(worker_output.get("evidence_required", True))
            model_claims = worker_output.get("claims")
            if isinstance(model_claims, list):
                for item in model_claims:
                    if not isinstance(item, dict):
                        continue
                    claims.append(
                        self._claim(
                            result.task_id,
                            str(item.get("text", "")).strip(),
                            [str(ref) for ref in item.get("evidence_refs", []) if ref],
                            evidence_required,
                            valid_chunk_ids,
                            consumed_chunk_refs_by_task,
                            chunks,
                        )
                    )
                continue
            claims.append(
                self._claim(
                    result.task_id,
                    str(worker_output.get("summary", "")).strip(),
                    [str(ref) for ref in worker_output.get("evidence_refs", []) if ref],
                    evidence_required,
                    valid_chunk_ids,
                    consumed_chunk_refs_by_task,
                    chunks,
                )
            )
        return claims

    def _claim(
        self,
        task_id: str,
        text: str,
        refs: list[str],
        evidence_required: bool,
        valid_chunk_ids: set[str],
        consumed_chunk_refs_by_task: dict[str, set[str]],
        chunks: list[ContextChunk],
    ) -> EvidenceClaim:
        evidence_resolved = (
            bool(refs)
            and all(ref in valid_chunk_ids for ref in refs)
            and set(refs).issubset(consumed_chunk_refs_by_task.get(task_id, set()))
        )
        consumed_ids = consumed_chunk_refs_by_task.get(task_id, set())
        delivered_chunks = [chunk for chunk in chunks if chunk.id in consumed_ids]
        verification = self.claim_verifier.verify(text, refs, delivered_chunks) if delivered_chunks else None
        citation_eligible = bool(text) and evidence_resolved and (
            verification is None or verification.status != ClaimVerificationStatus.CONTRADICTED
        )
        blocked_reason = None
        if not evidence_resolved and evidence_required:
            blocked_reason = "Evidence references were not resolved and consumed by this task."
        elif verification is not None and verification.status == ClaimVerificationStatus.CONTRADICTED:
            blocked_reason = verification.warning or "Configured claim verifier contradicted the claim."
        return EvidenceClaim(
            task_id=task_id,
            claim=text,
            evidence_refs=refs,
            evidence_required=evidence_required,
            resolved=bool(text) and (evidence_resolved if evidence_required else not refs),
            citation_eligible=citation_eligible,
            blocked_reason=blocked_reason,
            verification=verification,
        )
