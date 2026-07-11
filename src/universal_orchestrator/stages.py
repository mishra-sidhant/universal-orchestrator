from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from universal_orchestrator.models import (
    Artifact,
    ContextCard,
    ContextChunk,
    ContextManifest,
    ContextPack,
    ExecutionPolicy,
    ExecutionResult,
    ProductContract,
    QualityGateResult,
    RoutingAction,
    RoutingDecision,
    TaskNode,
    TaskStatus,
    utc_now,
)
from universal_orchestrator.cost_ledger import BudgetStopError
from universal_orchestrator.execution_policy import PolicyCompiler
from universal_orchestrator.model_synthesis import ModelOutputValidationError, ModelSynthesisRunner
from universal_orchestrator.providers.base import ProviderAdapterRegistry


@dataclass
class KernelStageContext:
    manifest: ContextManifest
    contract: ProductContract
    cards: list[ContextCard]
    chunks: list[ContextChunk]
    conflicts: list[str]
    chunk_refs_by_task: dict[str, list[str]]
    build_static_artifacts: Callable[[], list[Artifact]]
    evaluate_quality: Callable[[list[ExecutionResult]], QualityGateResult]
    context_packs: dict[str, ContextPack] = field(default_factory=dict)
    provider_adapters: ProviderAdapterRegistry | None = None
    operator_prompt: str = ""
    execution_policy: ExecutionPolicy | None = None
    provider_health_notices: list[str] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)


class StageWorkerRegistry:
    """Dispatches planned nodes to concrete local stage implementations."""

    def __init__(self, context: KernelStageContext) -> None:
        self.context = context
        self.observed_results: list[ExecutionResult] = []
        self.model_synthesis = ModelSynthesisRunner()
        self.handlers = {
            "T-AGGREGATE": self._aggregate,
            "T-GAP-ANALYSIS": self._gap_analysis,
            "T-SYNTHESIS": self._synthesis,
            "T-ARTIFACT-BUILD": self._artifact_build,
            "T-QUALITY": self._quality,
        }

    def execute(
        self, tasks: list[TaskNode], decisions: list[RoutingDecision]
    ) -> list[ExecutionResult]:
        decision_by_task = {decision.task_id: decision for decision in decisions}
        return [self._execute_one(task, decision_by_task[task.id]) for task in tasks]

    def execute_guarded(
        self,
        tasks: list[TaskNode],
        decisions: list[RoutingDecision],
        completion_guard,
    ) -> list[ExecutionResult]:
        if not completion_guard.is_active():
            return []
        results = self.execute(tasks, decisions)
        return results if completion_guard.is_active() else []

    def observe_result(self, result: ExecutionResult) -> None:
        self.observed_results.append(result)

    def _execute_one(self, task: TaskNode, decision: RoutingDecision) -> ExecutionResult:
        started_at = utc_now()
        evidence_required = task.id == "T-SYNTHESIS"
        refs = (
            list(self.context.chunk_refs_by_task.get(task.id, []))
            if evidence_required
            else []
        )
        if decision.action not in {RoutingAction.ROUTE, RoutingAction.ROUTE_DEGRADED}:
            status = (
                TaskStatus.WAITING_FOR_USER
                if decision.action == RoutingAction.PAUSE
                else TaskStatus.SKIPPED
            )
            return self._result(
                task,
                decision,
                status,
                decision.reason,
                [],
                refs,
                started_at,
                warnings=[decision.reason],
            )
        handler = self.handlers.get(task.id)
        if handler is None:
            reason = "No registered deterministic stage worker can execute this task."
            return self._result(
                task,
                decision,
                TaskStatus.SKIPPED,
                reason,
                [],
                [],
                started_at,
                warnings=[reason],
            )
        try:
            summary, findings, extra = handler(task, decision, refs)
            handler_warnings = list(extra.pop("_warnings", []))
            result = self._result(
                task,
                decision,
                TaskStatus.COMPLETED,
                summary,
                findings,
                refs,
                started_at,
                warnings=handler_warnings,
            )
            worker_output = dict(result.output["worker_output"])
            worker_output.update(extra)
            return result.model_copy(
                update={"output": {**result.output, "worker_output": worker_output}}
            )
        except Exception as exc:
            reason = f"Stage worker raised {type(exc).__name__}: {exc}"
            return self._result(
                task,
                decision,
                TaskStatus.FAILED,
                reason,
                [],
                [],
                started_at,
                warnings=[reason],
            )

    def _aggregate(
        self, task: TaskNode, decision: RoutingDecision, refs: list[str]
    ) -> tuple[str, list[dict], dict]:
        del task, decision, refs
        summary = (
            f"Aggregated {len(self.context.cards)} context card(s) and "
            f"{len(self.context.chunks)} chunk(s) from {len(self.context.manifest.inputs)} input(s)."
        )
        findings = [
            {
                "kind": "context_inventory",
                "severity": "info",
                "message": summary,
                "input_names": [item.name for item in self.context.manifest.inputs],
            }
        ]
        return summary, findings, {}

    def _gap_analysis(
        self, task: TaskNode, decision: RoutingDecision, refs: list[str]
    ) -> tuple[str, list[dict], dict]:
        del task, decision, refs
        partial = [
            item.name
            for item in self.context.manifest.inputs
            if str(item.status) in {"partial", "failed"}
        ]
        security_count = sum(
            len(item.security_findings) for item in self.context.manifest.inputs
        )
        gap_count = len(partial) + len(self.context.conflicts) + security_count
        summary = (
            f"Gap analysis found {gap_count} issue(s): {len(partial)} partial/failed input(s), "
            f"{len(self.context.conflicts)} conflict(s), and {security_count} security finding(s)."
        )
        findings = [
            {
                "kind": "gap_analysis",
                "severity": "medium" if gap_count else "info",
                "message": summary,
                "partial_inputs": partial,
                "conflicts": self.context.conflicts,
            }
        ]
        return summary, findings, {"gap_count": gap_count}

    def _synthesis(
        self, task: TaskNode, decision: RoutingDecision, refs: list[str]
    ) -> tuple[str, list[dict], dict]:
        adapter = (
            self.context.provider_adapters.get(decision.provider_id)
            if self.context.provider_adapters
            else None
        )
        if adapter and decision.provider_id != "deterministic.tools":
            if self.context.execution_policy:
                allowed, reason = PolicyCompiler().provider_allowed(
                    self.context.execution_policy, adapter.descriptor
                )
                if not allowed:
                    raise RuntimeError(reason)
            pack = self.context.context_packs.get(task.id)
            if pack is None:
                raise RuntimeError("Model synthesis requires a bounded context pack.")
            try:
                model_result = self.model_synthesis.run(
                    adapter,
                    task,
                    pack,
                    self.context.operator_prompt,
                )
            except BudgetStopError:
                raise
            except ModelOutputValidationError as exc:
                summary, findings, extra = self._extractive_synthesis(refs)
                return summary, findings, {
                    **extra,
                    "synthesis_path": "extractive_fallback",
                    "claims": [
                        {"text": summary, "evidence_refs": refs}
                    ] if refs else [],
                    "degraded_mode_notices": self.context.provider_health_notices,
                    "_warnings": [
                        f"Model output failed validation; used extractive synthesis fallback: {exc}"
                    ],
                }
            output = model_result.output
            evidence_refs = list(
                dict.fromkeys(ref for claim in output.claims for ref in claim.evidence_refs)
            )
            return output.summary, output.findings, {
                "synthesis_path": "model_repaired" if model_result.repaired else "model",
                "claims": [claim.model_dump(mode="json") for claim in output.claims],
                "evidence_refs": evidence_refs,
                "_warnings": model_result.warnings,
                "degraded_mode_notices": self.context.provider_health_notices,
            }
        summary, findings, extra = self._extractive_synthesis(refs)
        return summary, findings, {
            **extra,
            "synthesis_path": "extractive",
            "degraded_mode_notices": self.context.provider_health_notices,
        }

    def _extractive_synthesis(
        self,
        refs: list[str],
    ) -> tuple[str, list[dict], dict]:
        chunks_by_id = {chunk.id: chunk for chunk in self.context.chunks}
        consumed = [chunks_by_id[ref] for ref in refs if ref in chunks_by_id]
        excerpt = consumed[0].text[:180] if consumed else "No source passage was delivered."
        summary = f"Synthesized {len(consumed)} source passage(s): {excerpt}"
        findings = [
            {
                "kind": "source_excerpt",
                "severity": "info",
                "message": chunk.text[:240],
                "chunk_id": chunk.id,
                "locator": chunk.metadata.get("locator"),
            }
            for chunk in consumed
        ]
        return summary, findings, {"source_passage_count": len(consumed)}

    def _artifact_build(
        self, task: TaskNode, decision: RoutingDecision, refs: list[str]
    ) -> tuple[str, list[dict], dict]:
        del task, decision, refs
        self.context.artifacts = self.context.build_static_artifacts()
        names = [artifact.name for artifact in self.context.artifacts]
        summary = f"Built {len(names)} static run artifact(s)."
        return (
            summary,
            [
                {
                    "kind": "artifact_build",
                    "severity": "info",
                    "message": summary,
                    "artifact_names": names,
                }
            ],
            {"artifact_names": names},
        )

    def _quality(
        self, task: TaskNode, decision: RoutingDecision, refs: list[str]
    ) -> tuple[str, list[dict], dict]:
        provisional = self._result(
            task,
            decision,
            TaskStatus.COMPLETED,
            "Quality evaluation is executing.",
            [],
            refs,
            utc_now(),
        )
        quality = self.context.evaluate_quality([*self.observed_results, provisional])
        summary = (
            f"Evaluated runtime quality: passed={quality.passed}, "
            f"violations={len(quality.violations)}, warnings={len(quality.warnings)}."
        )
        findings = [
            {
                "kind": "quality_evaluation",
                "severity": "info" if quality.passed else "high",
                "message": summary,
            }
        ]
        return summary, findings, {"quality_result": quality.model_dump(mode="json")}

    def _result(
        self,
        task: TaskNode,
        decision: RoutingDecision,
        status: TaskStatus,
        summary: str,
        findings: list[dict],
        evidence_refs: list[str],
        started_at,
        warnings: list[str] | None = None,
    ) -> ExecutionResult:
        worker_output = {
            "task_id": task.id,
            "title": task.title,
            "task_type": task.task_type,
            "status": status,
            "summary": summary,
            "findings": findings,
            "evidence_refs": evidence_refs,
            "evidence_required": task.id == "T-SYNTHESIS",
            "files": [],
            "metrics": {
                "finding_count": len(findings),
                "consumed_chunk_count": len(evidence_refs),
            },
            "risks": [] if status == TaskStatus.COMPLETED else ["stage_not_completed"],
            "next_actions": [],
        }
        return ExecutionResult(
            task_id=task.id,
            provider_id=decision.provider_id,
            status=status,
            output={"title": task.title, "summary": summary, "worker_output": worker_output},
            warnings=warnings or [],
            started_at=started_at,
            completed_at=utc_now(),
        )
