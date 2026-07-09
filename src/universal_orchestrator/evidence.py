from __future__ import annotations

from universal_orchestrator.models import (
    ContextCard,
    EvidenceAuditFinding,
    EvidenceAuditReport,
    ExecutionResult,
    ProductPackage,
    ProvenanceRecord,
    QualityGateResult,
    TaskStatus,
)


class EvidenceAuditor:
    def audit(
        self,
        package: ProductPackage,
        cards: list[ContextCard],
        provenance: list[ProvenanceRecord],
        results: list[ExecutionResult],
    ) -> EvidenceAuditReport:
        cited_source_ids = sorted(self._worker_evidence_refs(results))
        unsupported_task_ids = sorted(self._unsupported_tasks(results))
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
                kind="worker_evidence",
                passed=not unsupported_task_ids,
                severity="medium",
                message="Completed worker outputs include evidence references.",
                metadata={"unsupported_task_ids": unsupported_task_ids},
            ),
            EvidenceAuditFinding(
                kind="final_markdown_context",
                passed="## Context Used" in package.final_markdown,
                severity="medium",
                message="Final markdown includes an explicit context section.",
            ),
        ]
        passed = all(finding.passed for finding in findings if finding.severity in {"high", "critical"})
        passed = passed and not unsupported_task_ids and "## Context Used" in package.final_markdown
        return EvidenceAuditReport(
            run_id=package.run_id,
            passed=passed,
            source_count=len(cards),
            provenance_count=len(provenance),
            cited_source_ids=cited_source_ids,
            unsupported_task_ids=unsupported_task_ids,
            findings=findings,
        )

    def apply_to_quality(
        self,
        quality: QualityGateResult,
        audit: EvidenceAuditReport,
        source_required: bool,
    ) -> QualityGateResult:
        if audit.passed:
            improved = max(quality.scores.citation_support, 85 if source_required else 100)
            scores = quality.scores.model_copy(update={"citation_support": improved})
            return quality.model_copy(update={"scores": scores})

        message = "Evidence audit did not find sufficient support for the final package."
        scores = quality.scores.model_copy(update={"citation_support": min(quality.scores.citation_support, 55)})
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
            if result.status != TaskStatus.COMPLETED:
                continue
            worker_output = result.output.get("worker_output", {})
            if not isinstance(worker_output, dict) or not worker_output.get("evidence_refs"):
                unsupported.add(result.task_id)
        return unsupported
