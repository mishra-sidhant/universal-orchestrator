from __future__ import annotations

from typing import Any

from universal_orchestrator.models import (
    Artifact,
    DebugBundleManifest,
    ObservabilityReport,
    RunState,
    TraceSpan,
    utc_now,
)


class TraceRecorder:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._last_checkpoint = utc_now()
        self.spans: list[TraceSpan] = []

    def checkpoint(self, name: str, metadata: dict[str, Any] | None = None) -> None:
        completed = utc_now()
        duration_ms = (completed - self._last_checkpoint).total_seconds() * 1000
        self.spans.append(
            TraceSpan(
                name=name,
                started_at=self._last_checkpoint,
                completed_at=completed,
                duration_ms=round(duration_ms, 3),
                metadata=metadata or {},
            )
        )
        self._last_checkpoint = completed

    def report(
        self,
        final_state: RunState,
        event_count: int,
        artifact_count: int,
        warning_count: int,
    ) -> ObservabilityReport:
        return ObservabilityReport(
            run_id=self.run_id,
            spans=self.spans,
            final_state=final_state,
            event_count=event_count,
            artifact_count=artifact_count,
            warning_count=warning_count,
        )


class DebugBundleBuilder:
    def build(self, run_id: str, artifacts: list[Artifact]) -> DebugBundleManifest:
        artifact_names = sorted(artifact.name for artifact in artifacts)
        report_names = sorted(
            name
            for name in artifact_names
            if name.endswith(".md")
            or name.endswith(".pdf")
            or name.endswith(".docx")
            or name in {"quality_report.json", "validation_findings.json"}
        )
        trace_names = sorted(
            name
            for name in artifact_names
            if name in {
                "trace_report.json",
                "debug_bundle_manifest.json",
                "schedule_report.json",
                "routing_telemetry.json",
                "delta_execution_plan.json",
                "budget_report.json",
            }
        )
        return DebugBundleManifest(
            run_id=run_id,
            artifact_names=artifact_names,
            report_names=report_names,
            trace_names=trace_names,
            safe_to_share=False,
        )
