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
    task_succeeded,
)


class EvidenceAuditor:
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
        claims = self._claims(results, valid_chunk_ids, consumed)
        evidence_claims = [claim for claim in claims if claim.evidence_required]
        unsupported_task_ids = sorted(
            claim.task_id for claim in claims if not claim.resolved
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
            ref for claim in claims if claim.resolved for ref in claim.evidence_refs
        }
        source_by_chunk = {
            chunk_id: record.source_id
            for record in provenance
            for chunk_id in record.chunk_ids
        }
        cited_source_ids = sorted(
            {source_by_chunk[ref] for ref in supported_refs if ref in source_by_chunk}
        )
        final_citations_present = bool(package) and "## Sources" in package.final_markdown and all(
            f"[{ref}]" in package.final_markdown for ref in supported_refs
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
        passed = passed and not unsupported_task_ids and (final_citations_present if package else True)
        return EvidenceAuditReport(
            run_id=package.run_id if package else (run_id or "unknown"),
            passed=passed,
            source_count=len(cards),
            provenance_count=len(provenance),
            cited_source_ids=cited_source_ids,
            unsupported_task_ids=unsupported_task_ids,
            invalid_evidence_refs=invalid_evidence_refs,
            unconsumed_evidence_refs=unconsumed_evidence_refs,
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
        supported_claims = len([claim for claim in evidence_claims if claim.resolved])
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
        if source_required:
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
    ) -> list[EvidenceClaim]:
        claims: list[EvidenceClaim] = []
        for result in results:
            if not task_succeeded(result.status):
                continue
            worker_output = result.output.get("worker_output", {})
            if not isinstance(worker_output, dict):
                worker_output = {}
            refs = [str(ref) for ref in worker_output.get("evidence_refs", []) if ref]
            claim = str(worker_output.get("summary", "")).strip()
            evidence_required = bool(worker_output.get("evidence_required", True))
            evidence_resolved = (
                bool(refs)
                and all(ref in valid_chunk_ids for ref in refs)
                and set(refs).issubset(
                    consumed_chunk_refs_by_task.get(result.task_id, set())
                )
            )
            claims.append(
                EvidenceClaim(
                    task_id=result.task_id,
                    claim=claim,
                    evidence_refs=refs,
                    evidence_required=evidence_required,
                    resolved=bool(claim)
                    and (evidence_resolved if evidence_required else not refs),
                )
            )
        return claims
