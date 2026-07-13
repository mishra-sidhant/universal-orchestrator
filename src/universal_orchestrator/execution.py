from __future__ import annotations

from typing import Any

from universal_orchestrator.models import (
    ExecutionPolicy,
    ExecutionResult,
    ProviderTask,
    RoutingAction,
    RoutingDecision,
    TaskNode,
    TaskStatus,
    utc_now,
)
from universal_orchestrator.providers import ProviderAdapterRegistry
from universal_orchestrator.workers import StructuredWorkerOutputBuilder


class DeterministicExecutor:
    """Provider-aware executor with dry-run-safe external adapters."""

    def __init__(
        self,
        adapters: ProviderAdapterRegistry | None = None,
        prompt: str = "",
        allow_network: bool = False,
        dry_run_external: bool = True,
        context: dict[str, Any] | None = None,
        execution_policy: ExecutionPolicy | None = None,
    ) -> None:
        self.adapters = adapters
        self.prompt = prompt
        self.allow_network = allow_network
        self.dry_run_external = dry_run_external
        self.context = context or {}
        self.execution_policy = execution_policy
        self.output_builder = StructuredWorkerOutputBuilder()

    def execute(self, tasks: list[TaskNode], decisions: list[RoutingDecision]) -> list[ExecutionResult]:
        decision_by_task = {decision.task_id: decision for decision in decisions}
        results: list[ExecutionResult] = []
        for task in tasks:
            started_at = utc_now()
            decision = decision_by_task[task.id]
            refs_by_task = self.context.get("chunk_refs_by_task", {})
            consumed_refs = (
                list(refs_by_task.get(task.id, [])) if isinstance(refs_by_task, dict) else []
            )
            task_context = {
                key: value
                for key, value in self.context.items()
                if key not in {"chunk_refs", "chunk_refs_by_task"}
            }
            task_context["consumed_chunk_refs"] = consumed_refs
            context_packs = self.context.get("context_packs", {})
            if isinstance(context_packs, dict) and task.id in context_packs:
                pack = context_packs[task.id]
                task_context["context_pack"] = (
                    pack.model_dump(mode="json") if hasattr(pack, "model_dump") else pack
                )
            warnings: list[str] = []
            reshaped = decision.action == RoutingAction.RESHAPE
            execution_decision = decision
            if reshaped:
                execution_decision = decision.model_copy(
                    update={
                        "action": RoutingAction.ROUTE_DEGRADED,
                        "provider_id": "deterministic.tools",
                    }
                )
                warnings.append(
                    "Task was reshaped to the bounded deterministic local form; "
                    "the requested provider capability was unavailable."
                )
            status = TaskStatus.COMPLETED
            if decision.action == RoutingAction.PAUSE:
                status = TaskStatus.WAITING_FOR_USER
                warnings.append(decision.reason)
            elif execution_decision.action == RoutingAction.ROUTE_DEGRADED:
                warnings.append("Task ran in degraded deterministic mode.")

            provider_result = None
            adapter = self.adapters.get(execution_decision.provider_id) if self.adapters else None
            if adapter and execution_decision.action in {RoutingAction.ROUTE, RoutingAction.ROUTE_DEGRADED}:
                if self._provider_blocked(adapter.descriptor.kind):
                    status = TaskStatus.WAITING_FOR_USER
                    warnings.append("Provider execution blocked by effective execution policy.")
                else:
                    provider_result = adapter.execute(
                        ProviderTask(
                            task=task,
                            prompt=self.prompt,
                            context={
                                **task_context,
                            "routing_score": execution_decision.score,
                            "routing_reason": execution_decision.reason,
                            },
                            dry_run=self.dry_run_external and decision.provider_id != "deterministic.tools",
                            allow_network=self.allow_network,
                            timeout_seconds=task.timeout_seconds,
                        )
                    )
                    status = provider_result.status
                    warnings.extend(provider_result.warnings)

            worker_output = self.output_builder.build(
                task, execution_decision, provider_result, task_context, status
            )
            if reshaped:
                worker_output["synthesis_path"] = "deterministic_reshape"

            results.append(
                ExecutionResult(
                    task_id=task.id,
                    provider_id=execution_decision.provider_id,
                    status=status,
                    output={
                        "title": task.title,
                        "task_type": task.task_type,
                        "decision": decision.action,
                        "summary": worker_output["summary"],
                        "worker_output": worker_output,
                        "provider_output": provider_result.output if provider_result else None,
                    },
                    warnings=warnings,
                    started_at=started_at,
                    completed_at=utc_now(),
                )
            )
        return results

    def _provider_blocked(self, provider_kind: str) -> bool:
        if not self.execution_policy:
            return False
        return provider_kind == "hosted_model" and not self.execution_policy.allow_hosted_models
