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
    ) -> EvidenceAuditReport:
        evidence_refs = self._worker_evidence_refs(results)
        valid_chunk_ids = {chunk.id for chunk in chunks or []}
        invalid_evidence_refs = sorted(evidence_refs.difference(valid_chunk_ids))
        source_by_chunk = {
            chunk_id: record.source_id
            for record in provenance
            for chunk_id in record.chunk_ids
        }
        cited_source_ids = sorted(
            {source_by_chunk[ref] for ref in evidence_refs if ref in source_by_chunk}
        )
        unsupported_task_ids = sorted(self._unsupported_tasks(results))
        claims = self._claims(results, valid_chunk_ids)
        final_citations_present = bool(package) and "## Sources" in package.final_markdown and all(
            f"[{ref}]" in package.final_markdown for ref in evidence_refs
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
                passed=bool(evidence_refs) and not invalid_evidence_refs,
                severity="high",
                message="Worker evidence references resolve to extracted source chunks.",
                metadata={"invalid_evidence_refs": invalid_evidence_refs},
            ),
            EvidenceAuditFinding(
                kind="claim_support",
                passed=not unsupported_task_ids,
                severity="medium",
                message="Completed worker claims include resolvable evidence references.",
                metadata={
                    "unsupported_task_ids": unsupported_task_ids,
                    "supported_claims": len([claim for claim in claims if claim.resolved]),
                    "claim_count": len(claims),
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
            claims=claims,
            findings=findings,
        )

    def apply_to_quality(
        self,
        quality: QualityGateResult,
        audit: EvidenceAuditReport,
        source_required: bool,
    ) -> QualityGateResult:
        claim_count = len(audit.claims)
        supported_claims = len([claim for claim in audit.claims if claim.resolved])
        citation_score = round(100 * supported_claims / claim_count) if claim_count else 0
        if audit.passed:
            scores = quality.scores.model_copy(
                update={
                    "citation_support": citation_score,
                    "factuality": min(quality.scores.factuality, citation_score),
                }
            )
            return quality.model_copy(update={"scores": scores})

        message = "Evidence audit did not find sufficient support for the final package."
        scores = quality.scores.model_copy(
            update={
                "citation_support": citation_score,
                "factuality": min(quality.scores.factuality, citation_score),
            }
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

    def _unsupported_tasks(self, results: list[ExecutionResult]) -> set[str]:
        unsupported: set[str] = set()
        for result in results:
            if not task_succeeded(result.status):
                continue
            worker_output = result.output.get("worker_output", {})
            if not isinstance(worker_output, dict) or not worker_output.get("evidence_refs"):
                unsupported.add(result.task_id)
        return unsupported

    def _claims(
        self, results: list[ExecutionResult], valid_chunk_ids: set[str]
    ) -> list[EvidenceClaim]:
        claims: list[EvidenceClaim] = []
        for result in results:
            if not task_succeeded(result.status):
                continue
            worker_output = result.output.get("worker_output", {})
            if not isinstance(worker_output, dict):
                continue
            refs = [str(ref) for ref in worker_output.get("evidence_refs", []) if ref]
            claim = str(worker_output.get("summary", "")).strip()
            claims.append(
                EvidenceClaim(
                    task_id=result.task_id,
                    claim=claim,
                    evidence_refs=refs,
                    resolved=bool(claim and refs) and all(ref in valid_chunk_ids for ref in refs),
                )
            )
        return claims
