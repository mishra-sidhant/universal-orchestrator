from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from time import monotonic, sleep
from unittest.mock import patch

from universal_orchestrator.cache import ExactMatchCache
from universal_orchestrator.mcp import serve_stdio
from universal_orchestrator.models import (
    ExecutionResult,
    HostInvocation,
    RetryPolicy,
    RoutingAction,
    RoutingDecision,
    RunState,
    TaskDAG,
    TaskNode,
    TaskStatus,
    TaskType,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.runtime import RuntimeStore
from universal_orchestrator.scheduler import DAGScheduler


class GuardAwareExecutor:
    def __init__(self) -> None:
        self.late_commits: list[str] = []

    def execute(self, tasks, decisions):
        raise AssertionError("scheduler did not provide a completion guard")

    def execute_guarded(self, tasks, decisions, completion_guard):
        del decisions
        sleep(0.05)
        if completion_guard.is_active():
            self.late_commits.append(tasks[0].id)
        return [
            ExecutionResult(
                task_id=tasks[0].id,
                provider_id="deterministic.tools",
                status=TaskStatus.COMPLETED,
            )
        ]


class TrancheE4RuntimeTests(unittest.TestCase):
    def test_artifact_validation_failure_blocks_delivery_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = Orchestrator(Path(tmp) / "runs")
            with patch.object(
                orchestrator.artifact_builder,
                "validate_pdf",
                return_value=["forced render corruption"],
            ):
                result = orchestrator.run(HostInvocation(prompt="Create a PDF report"))

            run_dir = Path(result.artifact_dir)
            validation = json.loads((run_dir / "pdf_validation.json").read_text())
            quality = json.loads((run_dir / "quality_report.json").read_text())

        self.assertEqual(result.state, RunState.NEEDS_ATTENTION)
        self.assertFalse(result.quality.passed)
        self.assertEqual(validation["errors"], ["forced render corruption"])
        self.assertTrue(any("forced render corruption" in item for item in quality["violations"]))
        self.assertIsNone(result.manifest.delivery_receipt_path)

    def test_two_runs_on_one_orchestrator_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_source = root / "first.md"
            second_source = root / "second.md"
            first_source.write_text("ALPHA_ONLY evidence")
            second_source.write_text("BETA_ONLY evidence")
            orchestrator = Orchestrator(root / "runs")

            self.assertFalse(hasattr(orchestrator, "executor"))
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(
                        orchestrator.run,
                        HostInvocation(prompt="Summarize source", attachments=[{"uri": str(path)}]),
                    )
                    for path in (first_source, second_source)
                ]
                first, second = [future.result() for future in futures]

            first_text = (Path(first.artifact_dir) / "context_chunks.json").read_text()
            second_text = (Path(second.artifact_dir) / "context_chunks.json").read_text()
            self.assertIn("ALPHA_ONLY", first_text)
            self.assertNotIn("BETA_ONLY", first_text)
            self.assertIn("BETA_ONLY", second_text)
            self.assertNotIn("ALPHA_ONLY", second_text)

    def test_runtime_store_enables_wal_and_busy_timeout_on_every_connection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RuntimeStore(Path(tmp) / "runtime.sqlite3")
            first = store._connect()
            second = store._connect()
            try:
                self.assertEqual(first.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                self.assertGreaterEqual(first.execute("PRAGMA busy_timeout").fetchone()[0], 5_000)
                self.assertEqual(second.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                self.assertGreaterEqual(second.execute("PRAGMA busy_timeout").fetchone()[0], 5_000)
            finally:
                first.close()
                second.close()

    def test_timed_out_worker_cannot_commit_after_terminal_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = ExactMatchCache(Path(tmp) / "cache")
            scheduler = DAGScheduler(cache)
            task = TaskNode(
                id="T-TIMEOUT",
                run_id="run_timeout",
                title="Timeout",
                task_type=TaskType.VALIDATION,
                timeout_seconds=0,
            )
            decision = RoutingDecision(
                task_id=task.id,
                action=RoutingAction.ROUTE,
                provider_id="deterministic.tools",
                reason="test",
            )
            executor = GuardAwareExecutor()
            results, report = scheduler.execute(
                TaskDAG(run_id=task.run_id, nodes=[task]),
                [decision],
                executor,
            )
            sleep(0.08)

            self.assertEqual(results[0].status, TaskStatus.FAILED)
            self.assertIn("timed out", results[0].warnings[0])
            self.assertEqual(executor.late_commits, [])
            self.assertEqual(len(report.records), 1)
            self.assertEqual(report.records[0].status, TaskStatus.FAILED)
            self.assertIsNone(cache.get(scheduler.cache_key_for_task(task)))

    def test_pipeline_emits_only_live_states_at_real_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = Orchestrator(Path(tmp) / "runs")
            result = orchestrator.run(HostInvocation(prompt="Produce a final report"))
            with closing(sqlite3.connect(orchestrator.runtime.path)) as conn:
                states = [
                    row[0]
                    for row in conn.execute(
                        "SELECT state FROM state_transitions WHERE run_id=? ORDER BY id",
                        (result.run_id,),
                    )
                ]

            for state in (
                RunState.FINAL_ASSEMBLY,
                RunState.ARTIFACT_BUILD,
                RunState.ARTIFACT_VALIDATION,
                RunState.PACKAGING,
            ):
                self.assertIn(state, states)
            self.assertFalse(hasattr(RunState, "PLAN_REVIEW"))
            self.assertFalse(hasattr(RunState, "AGGREGATING"))
            self.assertFalse(hasattr(RunState, "GAP_ANALYSIS"))

    def test_failure_artifact_names_the_true_post_dag_stage(self) -> None:
        cases = [
            ("Produce a final report", "product_owner", "assemble", RunState.FINAL_ASSEMBLY),
            ("Create a PDF report", "artifact_builder", "build_pdf", RunState.ARTIFACT_BUILD),
            (
                "Create a PDF report",
                "artifact_builder",
                "validate_pdf",
                RunState.ARTIFACT_VALIDATION,
            ),
            ("Produce a final report", "artifact_builder", "build_zip", RunState.PACKAGING),
        ]
        for prompt, owner_name, method_name, expected_state in cases:
            with self.subTest(stage=expected_state), tempfile.TemporaryDirectory() as tmp:
                orchestrator = Orchestrator(Path(tmp) / "runs")
                owner = getattr(orchestrator, owner_name)
                with patch.object(owner, method_name, side_effect=RuntimeError("forced stage failure")):
                    if method_name == "build_zip":
                        result = orchestrator.run(HostInvocation(prompt=prompt))
                    else:
                        with self.assertRaisesRegex(RuntimeError, "forced stage failure"):
                            orchestrator.run(HostInvocation(prompt=prompt))

                run_dir = next(
                    path
                    for path in (Path(tmp) / "runs").iterdir()
                    if path.name.startswith("run_")
                )
                if method_name == "build_zip":
                    self.assertEqual(result.state, RunState.NEEDS_ATTENTION)
                    zip_validation = json.loads((run_dir / "zip_validation.json").read_text())
                    self.assertTrue(
                        any("forced stage failure" in error for error in zip_validation["errors"])
                    )
                else:
                    failure = json.loads((run_dir / "failure.json").read_text())
                    self.assertEqual(failure["stage"], expected_state)

    def test_failed_quality_enters_repair_execution_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = Orchestrator(Path(tmp) / "runs")
            original = orchestrator.quality.evaluate

            def fail_quality(*args, **kwargs):
                result = original(*args, **kwargs)
                return result.model_copy(
                    update={"passed": False, "violations": [*result.violations, "forced"]}
                )

            with patch.object(orchestrator.quality, "evaluate", side_effect=fail_quality):
                result = orchestrator.run(HostInvocation(prompt="Produce a final report"))

            with closing(sqlite3.connect(orchestrator.runtime.path)) as conn:
                states = [
                    row[0]
                    for row in conn.execute(
                        "SELECT state FROM state_transitions WHERE run_id=? ORDER BY id",
                        (result.run_id,),
                    )
                ]
            self.assertIn(RunState.REPAIR_EXECUTION, states)

    def test_artifact_build_retries_once_in_a_real_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = Orchestrator(Path(tmp) / "runs")
            original = orchestrator._build_static_artifacts
            calls = 0

            def flaky_build(**kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("transient artifact failure")
                return original(**kwargs)

            with patch.object(orchestrator, "_build_static_artifacts", side_effect=flaky_build):
                result = orchestrator.run(HostInvocation(prompt="Produce a final report"))

            with closing(sqlite3.connect(orchestrator.runtime.path)) as conn:
                build_attempts = conn.execute(
                    "SELECT attempt, status FROM task_attempts "
                    "WHERE run_id=? AND task_id='T-ARTIFACT-BUILD' ORDER BY id",
                    (result.run_id,),
                ).fetchall()
            self.assertEqual(calls, 2)
            self.assertEqual(build_attempts, [(1, "failed"), (2, "completed")])

    def test_mcp_recovers_from_bad_json_and_ignores_notifications(self) -> None:
        stdin = io.StringIO(
            "not-json\n"
            + json.dumps({"jsonrpc": "2.0", "method": "ping"})
            + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"})
            + "\n"
        )
        stdout = io.StringIO()

        serve_stdio(stdin, stdout)

        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0]["error"]["code"], -32700)
        self.assertEqual(responses[1]["id"], 7)

    def test_mcp_can_process_cancel_while_run_request_is_active(self) -> None:
        run_started = threading.Event()
        cancel_processed = threading.Event()
        run_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ai_team.run", "arguments": {"prompt": "wait"}},
        }
        cancel_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "ai_team.cancel", "arguments": {"run_id": "run_wait"}},
        }

        def fake_call_tool(name, arguments=None):
            del arguments
            if name == "ai_team.run":
                run_started.set()
                self.assertTrue(cancel_processed.wait(1))
                return {"state": "cancelled"}
            self.assertTrue(run_started.wait(1))
            cancel_processed.set()
            return {"accepted": True, "cancelled": True}

        stdout = io.StringIO()
        started_at = monotonic()
        with patch("universal_orchestrator.mcp.call_tool", side_effect=fake_call_tool):
            serve_stdio(
                io.StringIO(json.dumps(run_request) + "\n" + json.dumps(cancel_request) + "\n"),
                stdout,
            )

        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertLess(monotonic() - started_at, 0.5)
        self.assertEqual({response["id"] for response in responses}, {1, 2})
        self.assertTrue(all("result" in response for response in responses))
        self.assertTrue(cancel_processed.is_set())

    def test_artifact_build_node_has_live_retry_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = Orchestrator(Path(tmp) / "runs")
            contract = orchestrator.contracts.compile(
                HostInvocation(prompt="Produce a final report"),
                orchestrator.ingestor.ingest(HostInvocation(prompt="Produce a final report"), "run_plan"),
            )
            dag = orchestrator.planner.create_execution_plan("run_plan", contract)
            node = next(item for item in dag.nodes if item.id == "T-ARTIFACT-BUILD")

        self.assertEqual(node.retry_policy, RetryPolicy(max_attempts=2))


if __name__ == "__main__":
    unittest.main()
