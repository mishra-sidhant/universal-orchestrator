from __future__ import annotations

from universal_orchestrator.models import (
    ContextCard,
    ContextManifest,
    ExecutionResult,
    ProductContract,
    ProductPackage,
    QualityGateResult,
    RoutingDecision,
    TaskDAG,
    TaskStatus,
)


class FinalProductOwner:
    def assemble(
        self,
        manifest: ContextManifest,
        contract: ProductContract,
        cards: list[ContextCard],
        dag: TaskDAG,
        decisions: list[RoutingDecision],
        results: list[ExecutionResult],
        quality: QualityGateResult,
    ) -> ProductPackage:
        rejected = self._reject_fragments(results)
        markdown = self._render_markdown(manifest, contract, cards, dag, decisions, results, quality, rejected)
        return ProductPackage(
            run_id=manifest.run_id,
            final_markdown=markdown,
            summary=f"Delivered {contract.run_type} package with {len(results)} execution result(s).",
            rejected_fragments=rejected,
            artifact_requests=contract.primary_artifacts,
            validation_notes=quality.warnings + quality.violations,
        )

    def _reject_fragments(self, results: list[ExecutionResult]) -> list[str]:
        rejected: list[str] = []
        for result in results:
            worker_output = result.output.get("worker_output")
            if result.status != TaskStatus.COMPLETED:
                rejected.append(f"{result.task_id}: status {result.status}")
            elif not isinstance(worker_output, dict):
                rejected.append(f"{result.task_id}: missing structured worker output")
            elif len(str(worker_output.get("summary", "")).strip()) < 10:
                rejected.append(f"{result.task_id}: summary too thin")
        return rejected

    def _render_markdown(
        self,
        manifest: ContextManifest,
        contract: ProductContract,
        cards: list[ContextCard],
        dag: TaskDAG,
        decisions: list[RoutingDecision],
        results: list[ExecutionResult],
        quality: QualityGateResult,
        rejected: list[str],
    ) -> str:
        lines = [
            "# Universal Orchestrator Final Product",
            "",
            f"Run ID: `{manifest.run_id}`",
            f"Run type: `{contract.run_type}`",
            f"Quality passed: `{quality.passed}`",
            "",
            "## Deliverable Contract",
            "",
            f"- Requested output: {contract.requested_output}",
            f"- Primary artifacts: {', '.join(contract.primary_artifacts)}",
            f"- Quality bar: {contract.quality_bar}",
            "",
            "## Context Used",
            "",
            f"- Inputs inventoried: {len(manifest.inputs)}",
            f"- Inputs parsed: {manifest.parsed_count}",
            f"- Context cards: {len(cards)}",
            "",
            "## Plan And Execution",
            "",
            f"- DAG tasks: {len(dag.nodes)}",
            f"- Routing decisions: {len(decisions)}",
            f"- Execution results: {len(results)}",
        ]
        if rejected:
            lines.extend(["", "## Rejected Fragments", ""])
            lines.extend(f"- {item}" for item in rejected)
        lines.extend(["", "## Key Findings", ""])
        for result in results[:12]:
            worker_output = result.output.get("worker_output", {})
            if isinstance(worker_output, dict):
                summary = worker_output.get("summary", "")
                risks = worker_output.get("risks", [])
                risk_text = f" Risks: {', '.join(risks)}." if risks else ""
                lines.append(f"- `{result.task_id}` {summary}{risk_text}")
        lines.extend(["", "## Quality", ""])
        lines.append(f"- Completeness: {quality.scores.completeness}")
        lines.append(f"- Artifact integrity: {quality.scores.artifact_integrity}")
        if quality.warnings:
            lines.append(f"- Warnings: {quality.warnings}")
        if quality.violations:
            lines.append(f"- Violations: {quality.violations}")
        lines.append("")
        return "\n".join(lines)

