from __future__ import annotations

import threading
import time
import unittest
from tempfile import TemporaryDirectory

from universal_orchestrator.models import (
    ExecutionResult,
    RoutingAction,
    RoutingDecision,
    TaskDAG,
    TaskNode,
    TaskStatus,
    TaskType,
    utc_now,
)
from universal_orchestrator.scheduler import DAGScheduler
from universal_orchestrator.runtime import RuntimeStore
from universal_orchestrator.models import TaskCheckpoint


class OverlapExecutor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def execute(self, tasks: list[TaskNode], decisions: list[RoutingDecision]) -> list[ExecutionResult]:
        del decisions
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.05)
        with self._lock:
            self.active -= 1
        now = utc_now()
        return [
            ExecutionResult(
                task_id=task.id,
                provider_id="fixture",
                status=TaskStatus.COMPLETED,
                output={"summary": task.id},
                started_at=now,
                completed_at=utc_now(),
            )
            for task in tasks
        ]


class ParallelSchedulerTests(unittest.TestCase):
    def test_resume_consumes_matching_validated_checkpoint_without_reexecution(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = RuntimeStore(f"{directory}/runtime.sqlite3")
            dag = TaskDAG(
                run_id="R",
                nodes=[TaskNode(id="A", run_id="R", title="A", task_type=TaskType.PLANNING)],
            )
            decision = RoutingDecision(
                task_id="A", action=RoutingAction.ROUTE, provider_id="fixture", reason="test"
            )
            DAGScheduler(runtime_store=runtime).execute(
                dag, [decision], OverlapExecutor(), {"input": "same"}
            )
            second_executor = OverlapExecutor()
            results, report = DAGScheduler(runtime_store=runtime).execute(
                dag, [decision], second_executor, {"input": "same"}
            )

            self.assertEqual(results[0].status, TaskStatus.CACHED)
            self.assertEqual(report.checkpoint_hits, ["A"])
            self.assertEqual(second_executor.max_active, 0)

    def test_resume_reexecutes_when_fingerprint_changes_or_task_is_side_effecting(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = RuntimeStore(f"{directory}/runtime.sqlite3")
            cacheable = TaskNode(id="A", run_id="R", title="A", task_type=TaskType.PLANNING)
            side_effecting = TaskNode(
                id="B",
                run_id="R",
                title="B",
                task_type=TaskType.ARTIFACT_BUILD,
                cacheable=False,
            )
            dag = TaskDAG(run_id="R", nodes=[cacheable, side_effecting])
            decisions = [
                RoutingDecision(
                    task_id=task.id,
                    action=RoutingAction.ROUTE,
                    provider_id="fixture",
                    reason="test",
                )
                for task in dag.nodes
            ]
            DAGScheduler(runtime_store=runtime).execute(
                dag, decisions, OverlapExecutor(), {"input": "same"}
            )
            results, report = DAGScheduler(runtime_store=runtime).execute(
                dag, decisions, OverlapExecutor(), {"input": "changed"}
            )

            self.assertEqual(report.checkpoint_hits, ["A"])
            self.assertEqual(
                [result.status for result in results],
                [TaskStatus.CACHED, TaskStatus.COMPLETED],
            )

    def test_independent_tasks_overlap_and_dependents_wait(self) -> None:
        dag = TaskDAG(
            run_id="R",
            nodes=[
                TaskNode(id="A", run_id="R", title="A", task_type=TaskType.PLANNING),
                TaskNode(id="B", run_id="R", title="B", task_type=TaskType.PLANNING),
                TaskNode(
                    id="C",
                    run_id="R",
                    title="C",
                    task_type=TaskType.PLANNING,
                    dependencies=["A", "B"],
                ),
            ],
        )
        decisions = [
            RoutingDecision(task_id=task_id, action=RoutingAction.ROUTE, provider_id="fixture", reason="test")
            for task_id in ("A", "B", "C")
        ]
        executor = OverlapExecutor()

        results, report = DAGScheduler(max_parallel_tasks=2).execute(dag, decisions, executor)

        self.assertGreaterEqual(executor.max_active, 2)
        self.assertEqual([result.task_id for result in results], ["A", "B", "C"])
        self.assertEqual(report.parallel_batches, [["A", "B"], ["C"]])

    def test_sqlite_lease_fences_checkpoints_and_rolls_epoch(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = RuntimeStore(f"{directory}/runtime.sqlite3")
            first = runtime.acquire_task_lease("R", "T", "worker-1", ttl_seconds=30)
            self.assertIsNotNone(first)
            assert first is not None
            self.assertIsNone(runtime.acquire_task_lease("R", "T", "worker-2", ttl_seconds=30))

            checkpoint = TaskCheckpoint(
                run_id="R",
                task_id="T",
                attempt=1,
                sequence=1,
                lease_epoch=first.epoch,
                validated_output={"summary": "validated"},
            )
            self.assertTrue(runtime.save_checkpoint(checkpoint, first))
            self.assertEqual(runtime.latest_checkpoint("R", "T").validated_output["summary"], "validated")
            self.assertTrue(runtime.release_task_lease(first, "completed"))

            second = runtime.acquire_task_lease("R", "T", "worker-2", ttl_seconds=30, attempt=2)
            self.assertIsNotNone(second)
            assert second is not None
            self.assertGreater(second.epoch, first.epoch)
            self.assertFalse(runtime.save_checkpoint(checkpoint, first))

    def test_scheduler_persists_only_completed_validated_output(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = RuntimeStore(f"{directory}/runtime.sqlite3")
            dag = TaskDAG(
                run_id="R",
                nodes=[TaskNode(id="A", run_id="R", title="A", task_type=TaskType.PLANNING)],
            )
            decision = RoutingDecision(
                task_id="A", action=RoutingAction.ROUTE, provider_id="fixture", reason="test"
            )
            executor = OverlapExecutor()

            results, _ = DAGScheduler(runtime_store=runtime).execute(dag, [decision], executor)

            self.assertEqual(results[0].status, TaskStatus.COMPLETED)
            checkpoint = runtime.latest_checkpoint("R", "A")
            self.assertIsNotNone(checkpoint)
            assert checkpoint is not None
            self.assertEqual(checkpoint.validated_output["summary"], "A")


if __name__ == "__main__":
    unittest.main()
