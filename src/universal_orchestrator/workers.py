from __future__ import annotations

from typing import Any

from universal_orchestrator.models import ProviderResult, RoutingAction, RoutingDecision, TaskNode, TaskStatus, TaskType


class StructuredWorkerOutputBuilder:
    def build(
        self,
        task: TaskNode,
        decision: RoutingDecision,
        provider_result: ProviderResult | None,
        context: dict[str, Any],
        status: TaskStatus,
    ) -> dict[str, Any]:
        output = {
            "task_id": task.id,
            "title": task.title,
            "task_type": task.task_type,
            "status": status,
            "summary": self._summary(task, decision, provider_result),
            "findings": self._findings(task, decision, provider_result, context),
            "evidence_refs": self._evidence_refs(context),
            "files": self._files(task, context),
            "metrics": self._metrics(task, decision, provider_result, context),
            "risks": self._risks(task, decision, provider_result),
            "next_actions": self._next_actions(task, decision, status),
        }
        return output

    def _summary(
        self,
        task: TaskNode,
        decision: RoutingDecision,
        provider_result: ProviderResult | None,
    ) -> str:
        provider_summary = ""
        if provider_result:
            provider_summary = str(provider_result.output.get("summary", ""))
        if provider_summary:
            return provider_summary
        return f"{task.title} routed with action={decision.action}."

    def _findings(
        self,
        task: TaskNode,
        decision: RoutingDecision,
        provider_result: ProviderResult | None,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        findings = [
            {
                "kind": "routing",
                "severity": "info",
                "message": decision.reason,
                "provider_id": decision.provider_id,
                "score": decision.score,
            }
        ]
        if decision.action == RoutingAction.ROUTE_DEGRADED:
            findings.append(
                {
                    "kind": "capability_gap",
                    "severity": "medium",
                    "message": "Task completed with the best available provider below requested capability thresholds.",
                }
            )
        if provider_result and provider_result.warnings:
            findings.extend(
                {
                    "kind": "provider_warning",
                    "severity": "medium",
                    "message": warning,
                }
                for warning in provider_result.warnings
            )
        if task.task_type == TaskType.PLANNING:
            findings.append(
                {
                    "kind": "plan_integrity",
                    "severity": "info",
                    "message": "Task participates in the typed execution DAG and preserves dependency traceability.",
                }
            )
        if task.task_type == TaskType.VALIDATION:
            findings.append(
                {
                    "kind": "validation_scope",
                    "severity": "info",
                    "message": "Validation task checks contract, routing, security, artifact, or continuity concerns.",
                }
            )
        if task.task_type == TaskType.ARTIFACT_BUILD:
            findings.append(
                {
                    "kind": "artifact_package",
                    "severity": "info",
                    "message": "Artifact package should include manifests, reports, execution trace, and quality output.",
                }
            )
        if task.task_type == TaskType.QUALITY_REPAIR:
            findings.append(
                {
                    "kind": "targeted_repair",
                    "severity": "info",
                    "message": "Repair task targets a specific quality violation rather than regenerating the full run.",
                }
            )
        if context.get("security_findings_count", 0):
            findings.append(
                {
                    "kind": "security_context",
                    "severity": "medium",
                    "message": f"{context['security_findings_count']} security finding(s) were available to this worker.",
                }
            )
        return findings

    def _evidence_refs(self, context: dict[str, Any]) -> list[str]:
        return list(context.get("input_refs", []))[:20]

    def _files(self, task: TaskNode, context: dict[str, Any]) -> list[dict[str, str]]:
        if task.task_type not in {TaskType.CODE_EDIT, TaskType.CODE_REVIEW, TaskType.RESEARCH, TaskType.SUMMARIZATION}:
            return []
        return [{"path": path, "role": "read"} for path in context.get("files", [])[:20]]

    def _metrics(
        self,
        task: TaskNode,
        decision: RoutingDecision,
        provider_result: ProviderResult | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "dependency_count": len(task.dependencies),
            "required_capability_count": len(task.required_capabilities),
            "routing_score": decision.score,
            "provider_status": provider_result.status if provider_result else None,
            "available_input_count": len(context.get("input_refs", [])),
            "available_file_count": len(context.get("files", [])),
        }

    def _risks(
        self,
        task: TaskNode,
        decision: RoutingDecision,
        provider_result: ProviderResult | None,
    ) -> list[str]:
        risks: list[str] = []
        if decision.action == RoutingAction.ROUTE_DEGRADED:
            risks.append("degraded_provider_capability")
        if decision.action in {RoutingAction.RESHAPE, RoutingAction.PAUSE}:
            risks.append("work_not_executed")
        if provider_result and provider_result.status != TaskStatus.COMPLETED:
            risks.append("provider_result_not_completed")
        if task.criticality in {"high", "mission_critical"} and decision.action != RoutingAction.ROUTE:
            risks.append("critical_task_ran_below_ideal_route")
        return risks

    def _next_actions(
        self,
        task: TaskNode,
        decision: RoutingDecision,
        status: TaskStatus,
    ) -> list[str]:
        if status == TaskStatus.FAILED:
            return ["create targeted repair task"]
        if task.task_type == TaskType.QUALITY_REPAIR:
            return ["re-run affected quality gates", "preserve original run trace"]
        if decision.action == RoutingAction.ROUTE_DEGRADED:
            return ["rerun with stronger provider when configured", "increase validation scrutiny"]
        if task.task_type == TaskType.ARTIFACT_BUILD:
            return ["validate artifact paths", "include artifact links in final response"]
        return ["feed structured output to downstream dependent tasks"]
