from __future__ import annotations

from universal_orchestrator.models import ExecutionResult, RoutingAction, RoutingDecision, TaskNode, TaskStatus


class DeterministicExecutor:
    """MVP executor that records structured outputs without calling external models."""

    def execute(self, tasks: list[TaskNode], decisions: list[RoutingDecision]) -> list[ExecutionResult]:
        decision_by_task = {decision.task_id: decision for decision in decisions}
        results: list[ExecutionResult] = []
        for task in tasks:
            decision = decision_by_task[task.id]
            warnings: list[str] = []
            status = TaskStatus.COMPLETED
            if decision.action in {RoutingAction.RESHAPE, RoutingAction.PAUSE}:
                status = TaskStatus.WAITING_FOR_USER if decision.action == RoutingAction.PAUSE else TaskStatus.SKIPPED
                warnings.append(decision.reason)
            elif decision.action == RoutingAction.ROUTE_DEGRADED:
                warnings.append("Task ran in degraded deterministic mode.")

            results.append(
                ExecutionResult(
                    task_id=task.id,
                    provider_id=decision.provider_id,
                    status=status,
                    output={
                        "title": task.title,
                        "task_type": task.task_type,
                        "decision": decision.action,
                        "summary": self._summary(task, decision),
                    },
                    warnings=warnings,
                )
            )
        return results

    def _summary(self, task: TaskNode, decision: RoutingDecision) -> str:
        provider = decision.provider_id or "no provider"
        return f"{task.title} handled by {provider} with action={decision.action}."

