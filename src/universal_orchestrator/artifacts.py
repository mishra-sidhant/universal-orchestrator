from __future__ import annotations

from pathlib import Path
from typing import Any

from universal_orchestrator.models import (
    Artifact,
    ArtifactType,
    ContextCard,
    ContextManifest,
    ExecutionResult,
    ProductContract,
    QualityGateResult,
    RoutingDecision,
    RunManifest,
    TaskDAG,
)
from universal_orchestrator.utils import ensure_dir, sha256_file, write_json


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = ensure_dir(root)

    def run_dir(self, run_id: str) -> Path:
        return ensure_dir(self.root / run_id)

    def write_json_artifact(self, run_id: str, name: str, payload: Any) -> Artifact:
        path = self.run_dir(run_id) / name
        write_json(path, payload)
        return self._artifact(path, ArtifactType.JSON)

    def write_text_artifact(self, run_id: str, name: str, content: str, artifact_type: ArtifactType) -> Artifact:
        path = self.run_dir(run_id) / name
        ensure_dir(path.parent)
        path.write_text(content)
        return self._artifact(path, artifact_type)

    def write_final_report(
        self,
        run_id: str,
        manifest: ContextManifest,
        contract: ProductContract,
        cards: list[ContextCard],
        dag: TaskDAG,
        decisions: list[RoutingDecision],
        results: list[ExecutionResult],
        quality: QualityGateResult | None = None,
    ) -> Artifact:
        content = self._render_report(manifest, contract, cards, dag, decisions, results, quality)
        return self.write_text_artifact(run_id, "final_report.md", content, ArtifactType.REPORT)

    def write_run_manifest(self, run_manifest: RunManifest) -> Artifact:
        path = self.run_dir(run_manifest.run_id) / "run_manifest.json"
        write_json(path, run_manifest.model_dump(mode="json"))
        return self._artifact(path, ArtifactType.MANIFEST)

    def _artifact(self, path: Path, artifact_type: ArtifactType) -> Artifact:
        return Artifact(
            type=artifact_type,
            name=path.name,
            path=str(path),
            content_hash=sha256_file(path),
            size_bytes=path.stat().st_size,
        )

    def _render_report(
        self,
        manifest: ContextManifest,
        contract: ProductContract,
        cards: list[ContextCard],
        dag: TaskDAG,
        decisions: list[RoutingDecision],
        results: list[ExecutionResult],
        quality: QualityGateResult | None,
    ) -> str:
        lines = [
            "# Universal Orchestrator Run Report",
            "",
            f"Run ID: `{manifest.run_id}`",
            f"Invocation ID: `{manifest.invocation_id}`",
            "",
            "## Product Contract",
            "",
            f"- Run type: `{contract.run_type}`",
            f"- Requested output: {contract.requested_output}",
            f"- Primary artifacts: {', '.join(contract.primary_artifacts)}",
            f"- Quality bar: {contract.quality_bar}",
            "",
            "## Context Manifest",
            "",
            f"- Inputs inventoried: {len(manifest.inputs)}",
            f"- Inputs parsed: {manifest.parsed_count}",
        ]
        if manifest.warnings:
            lines.append(f"- Manifest warnings: {len(manifest.warnings)}")
        lines.extend(["", "## Top Context Cards", ""])
        for card in sorted(cards, key=lambda item: item.relevance_score, reverse=True)[:8]:
            lines.append(f"- `{card.card_type}` {card.title}: {card.summary}")

        lines.extend(["", "## Execution DAG", ""])
        for node in dag.topological_order():
            deps = ", ".join(node.dependencies) if node.dependencies else "none"
            lines.append(f"- `{node.id}` {node.title} ({node.task_type}); deps: {deps}")

        lines.extend(["", "## Routing Decisions", ""])
        for decision in decisions:
            provider = decision.provider_id or "none"
            lines.append(f"- `{decision.task_id}` -> `{decision.action}` via `{provider}`: {decision.reason}")

        lines.extend(["", "## Execution Results", ""])
        for result in results:
            worker_output = result.output.get("worker_output", {})
            summary = worker_output.get("summary", result.output.get("summary", ""))
            findings = len(worker_output.get("findings", [])) if isinstance(worker_output, dict) else 0
            risks = worker_output.get("risks", []) if isinstance(worker_output, dict) else []
            risk_text = f"; risks: {', '.join(risks)}" if risks else ""
            lines.append(
                f"- `{result.task_id}` `{result.status}` provider=`{result.provider_id}` "
                f"findings={findings}{risk_text}: {summary}"
            )

        if quality:
            lines.extend(["", "## Quality", ""])
            lines.append(f"- Passed: `{quality.passed}`")
            lines.append(f"- Artifact integrity: `{quality.scores.artifact_integrity}`")
            if quality.violations:
                lines.append(f"- Violations: {quality.violations}")
            if quality.warnings:
                lines.append(f"- Warnings: {quality.warnings}")

        lines.extend(
            [
                "",
                "## Residual Risks",
                "",
                "- Hosted provider calls are not implemented in this deterministic MVP.",
                "- DOCX, PPTX, spreadsheet, image OCR, archive unpacking, and URL fetchers are inventoried but not fully parsed yet.",
                "- Targeted repair is represented in the quality result and will become executable DAG work in the next milestone.",
                "",
            ]
        )
        return "\n".join(lines)
