from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from threading import Event, Lock
from time import sleep
from typing import Any, Callable, cast

from universal_orchestrator.cache import ExactMatchCache
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


class CompletionGuard:
    """Cooperative lease that closes when the scheduler declares a timeout."""

    def __init__(self) -> None:
        self._active = Event()
        self._active.set()
        self._lock = Lock()
        self._cleanups: list[Callable[[], None]] = []

    def is_active(self) -> bool:
        return self._active.is_set()

    def deactivate(self) -> None:
        with self._lock:
            self._active.clear()
            cleanups = list(self._cleanups)
            self._cleanups.clear()
        for cleanup in cleanups:
            cleanup()

    def register_cleanup(self, cleanup: Callable[[], None]) -> None:
        run_now = False
        with self._lock:
            if self._active.is_set():
                self._cleanups.append(cleanup)
            else:
                run_now = True
        if run_now:
            cleanup()

    def commit_if_active(self, commit: Callable[[], None]) -> bool:
        with self._lock:
            if not self._active.is_set():
                return False
            commit()
            return True


class DAGScheduler:
    def __init__(self, cache: ExactMatchCache | None = None) -> None:
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
        executor: Any,
        cache_context: dict[str, Any] | None = None,
        cancellation_check: Callable[[], bool] | None = None,
    ) -> tuple[list[ExecutionResult], ScheduleReport]:
        decision_by_task = {decision.task_id: decision for decision in decisions}
        results: list[ExecutionResult] = []
        records: list[ScheduledTaskRecord] = []
        cache_hits: list[str] = []
        execution_order: list[str] = []
        result_by_task: dict[str, ExecutionResult] = {}
        for batch in self.parallel_batches(dag):
            for task in batch:
                cache_key = self.cache_key_for_task(task, cache_context)
                if cancellation_check and cancellation_check():
                    result = self._terminal_result(
                        task,
                        TaskStatus.CANCELLED,
                        "Run cancellation requested before task execution.",
                    )
                    records.append(self._record(task, result, 0, cache_key))
                elif self._blocked_by_dependency(task, result_by_task):
                    result = self._terminal_result(
                        task,
                        TaskStatus.SKIPPED,
                        "Task skipped because a dependency did not complete successfully.",
                    )
                    records.append(self._record(task, result, 0, cache_key))
                else:
                    cached = self.cached_payload(cache_key, task.cacheable)
                    if cached and cached.get("schema_version") == "2.0" and cached.get("status") == "completed":
                        cache_hits.append(task.id)
                        result = ExecutionResult(
                            task_id=task.id,
                            provider_id=cached.get("provider_id"),
                            status=TaskStatus.CACHED,
                            output=cached.get("output", {}),
                            warnings=["Loaded from scheduler cache."],
                            started_at=utc_now(),
                            completed_at=utc_now(),
                        )
                        records.append(self._record(task, result, 0, cache_key))
                    else:
                        result = self._execute_with_retries(
                            task,
                            decision_by_task[task.id],
                            executor,
                            cache_key,
                            records,
                            cancellation_check,
                        )
                        if self.cache and task.cacheable and result.status == TaskStatus.COMPLETED:
                            self.cache.set(
                                cache_key,
                                {
                                    "schema_version": "2.0",
                                    "provider_id": result.provider_id,
                                    "status": "completed",
                                    "output": result.output,
                                },
                            )
                results.append(result)
                result_by_task[task.id] = result
                execution_order.append(task.id)
                observer = getattr(executor, "observe_result", None)
                if callable(observer):
                    observer(result)
        report = ScheduleReport(
            run_id=dag.run_id,
            records=records,
            execution_order=execution_order,
            parallel_batches=[[task.id for task in batch] for batch in self.parallel_batches(dag)],
            cache_hits=cache_hits,
            failed_tasks=[result.task_id for result in results if result.status == TaskStatus.FAILED],
        )
        return results, report

    def _execute_with_retries(
        self,
        task: TaskNode,
        decision: RoutingDecision,
        executor: DeterministicExecutor,
        cache_key: str,
        records: list[ScheduledTaskRecord],
        cancellation_check: Callable[[], bool] | None,
    ) -> ExecutionResult:
        max_attempts = max(1, task.retry_policy.max_attempts)
        result = self._terminal_result(task, TaskStatus.FAILED, "Task did not execute.")
        for attempt in range(1, max_attempts + 1):
            if cancellation_check and cancellation_check():
                result = self._terminal_result(
                    task,
                    TaskStatus.CANCELLED,
                    "Run cancellation requested before retry attempt.",
                )
                records.append(self._record(task, result, attempt, cache_key))
                break
            result = self._execute_with_timeout(task, decision, executor)
            records.append(self._record(task, result, attempt, cache_key))
            if result.status == TaskStatus.COMPLETED:
                break
            if attempt < max_attempts and task.retry_policy.backoff_seconds > 0:
                sleep(task.retry_policy.backoff_seconds)
        return result

    def _execute_with_timeout(
        self,
        task: TaskNode,
        decision: RoutingDecision,
        executor: DeterministicExecutor,
    ) -> ExecutionResult:
        completion_guard = CompletionGuard()
        guarded_execute = getattr(executor, "execute_guarded", None)
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"uo-{task.id}")
        if callable(guarded_execute):
            future = pool.submit(guarded_execute, [task], [decision], completion_guard)
        else:
            future = pool.submit(executor.execute, [task], [decision])
        try:
            return cast(list[ExecutionResult], future.result(timeout=max(0, task.timeout_seconds)))[0]
        except FutureTimeoutError:
            completion_guard.deactivate()
            future.cancel()
            return self._terminal_result(
                task,
                TaskStatus.FAILED,
                f"Task timed out after {task.timeout_seconds} second(s).",
            )
        except Exception as exc:
            return self._terminal_result(
                task,
                TaskStatus.FAILED,
                f"Task execution raised {type(exc).__name__}: {exc}",
            )
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def _blocked_by_dependency(
        self,
        task: TaskNode,
        result_by_task: dict[str, ExecutionResult],
    ) -> bool:
        successful = {TaskStatus.COMPLETED, TaskStatus.CACHED}
        return any(
            dependency not in result_by_task
            or result_by_task[dependency].status not in successful
            for dependency in task.dependencies
        )

    def _terminal_result(self, task: TaskNode, status: TaskStatus, warning: str) -> ExecutionResult:
        now = utc_now()
        return ExecutionResult(
            task_id=task.id,
            provider_id=None,
            status=status,
            output={},
            warnings=[warning],
            started_at=now,
            completed_at=now,
        )

    def _record(
        self,
        task: TaskNode,
        result: ExecutionResult,
        attempt: int,
        cache_key: str,
    ) -> ScheduledTaskRecord:
        return ScheduledTaskRecord(
            task_id=task.id,
            status=result.status,
            attempt=attempt,
            dependencies=task.dependencies,
            cache_key=cache_key,
            started_at=result.started_at,
            completed_at=result.completed_at,
            warnings=result.warnings,
        )

    def cache_key_for_task(self, task: TaskNode, cache_context: dict[str, Any] | None = None) -> str:
        payload = {
            "task_id": task.id,
            "title": task.title,
            "task_type": task.task_type,
            "capabilities": task.required_capabilities,
            "dependencies": task.dependencies,
            "max_cost_tier": task.max_cost_tier,
            "cache_context": cache_context or {},
        }
        if self.cache:
            return self.cache.key_for("task", payload)
        return f"task_{task.id}"

    def cached_payload(self, cache_key: str, cacheable: bool = True) -> dict[str, Any] | None:
        return self.cache.get(cache_key) if self.cache and cacheable else None

    def cached_payload_for_task(
        self,
        task: TaskNode,
        cache_context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        return self.cached_payload(
            self.cache_key_for_task(task, cache_context),
            task.cacheable,
        )
