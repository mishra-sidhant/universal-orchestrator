from __future__ import annotations

from universal_orchestrator.cache import SemanticCache
from universal_orchestrator.execution import DeterministicExecutor
from universal_orchestrator.models import (
    ExecutionResult,
    RoutingDecision,
    ScheduleReport,
    ScheduledTaskRecord,
    TaskDAG,
    TaskNode,
    TaskStatus,
    utc_now,
)


class DAGScheduler:
    def __init__(self, cache: SemanticCache | None = None) -> None:
        self.cache = cache

    def parallel_batches(self, dag: TaskDAG) -> list[list[TaskNode]]:
        remaining = {node.id: node for node in dag.nodes}
        completed: set[str] = set()
        batches: list[list[TaskNode]] = []
        while remaining:
            ready = [
                node
                for node in remaining.values()
                if all(dependency in completed for dependency in node.dependencies)
            ]
            if not ready:
                dag.validate_graph()
                raise ValueError("DAG has no schedulable tasks but still has remaining nodes.")
            ready = sorted(ready, key=lambda node: node.id)
            batches.append(ready)
            for node in ready:
                completed.add(node.id)
                remaining.pop(node.id)
        return batches

    def execute(
        self,
        dag: TaskDAG,
        decisions: list[RoutingDecision],
        executor: DeterministicExecutor,
    ) -> tuple[list[ExecutionResult], ScheduleReport]:
        decision_by_task = {decision.task_id: decision for decision in decisions}
        results: list[ExecutionResult] = []
        records: list[ScheduledTaskRecord] = []
        cache_hits: list[str] = []
        execution_order: list[str] = []
        for batch in self.parallel_batches(dag):
            for task in batch:
                cache_key = self._cache_key(task)
                cached = self.cache.get(cache_key) if self.cache else None
                started = utc_now()
                if cached:
                    cache_hits.append(task.id)
                    result = ExecutionResult(
                        task_id=task.id,
                        provider_id=cached.get("provider_id"),
                        status=TaskStatus.CACHED,
                        output=cached.get("output", {}),
                        warnings=["Loaded from scheduler cache."],
                        started_at=started,
                        completed_at=utc_now(),
                    )
                else:
                    result = executor.execute([task], [decision_by_task[task.id]])[0]
                    if self.cache and result.status == TaskStatus.COMPLETED:
                        self.cache.set(
                            cache_key,
                            {
                                "provider_id": result.provider_id,
                                "status": result.status,
                                "output": result.output,
                            },
                        )
                results.append(result)
                execution_order.append(task.id)
                records.append(
                    ScheduledTaskRecord(
                        task_id=task.id,
                        status=result.status,
                        attempt=1,
                        dependencies=task.dependencies,
                        cache_key=cache_key,
                        started_at=result.started_at,
                        completed_at=result.completed_at,
                        warnings=result.warnings,
                    )
                )
        report = ScheduleReport(
            run_id=dag.run_id,
            records=records,
            execution_order=execution_order,
            parallel_batches=[[task.id for task in batch] for batch in self.parallel_batches(dag)],
            cache_hits=cache_hits,
            failed_tasks=[result.task_id for result in results if result.status == TaskStatus.FAILED],
        )
        return results, report

    def _cache_key(self, task: TaskNode) -> str:
        payload = {
            "task_id": task.id,
            "title": task.title,
            "task_type": task.task_type,
            "capabilities": task.required_capabilities,
            "dependencies": task.dependencies,
        }
        if self.cache:
            return self.cache.key_for("task", payload)
        return f"task_{task.id}"
