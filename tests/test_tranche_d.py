import tempfile
import unittest
import zipfile
from json import loads
from pathlib import Path
from time import sleep
from unittest.mock import patch

from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.cache import SemanticCache
from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.execution import DeterministicExecutor
from universal_orchestrator.execution_policy import PolicyCompiler
from universal_orchestrator.errors import RunCancelledError
from universal_orchestrator.evals import EvaluationRunner
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    CostTier,
    ExecutionResult,
    ExecutionPolicy,
    HostInvocation,
    PrivacyMode,
    ProviderDescriptor,
    ProviderHealth,
    ProviderKind,
    ProviderResult,
    ProviderStatus,
    RoutingAction,
    RoutingDecision,
    RetryPolicy,
    TaskDAG,
    TaskNode,
    TaskStatus,
    TaskType,
    UserOptions,
)
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.providers.base import ProviderAdapter, ProviderAdapterRegistry
from universal_orchestrator.routing import AdaptiveRouter, CapabilityRegistry
from universal_orchestrator.scheduler import DAGScheduler
from universal_orchestrator.utils import sha256_file, write_json


class RecordingHostedAdapter(ProviderAdapter):
    def __init__(self) -> None:
        super().__init__(
            ProviderDescriptor(
                id="hosted.test",
                kind=ProviderKind.HOSTED_MODEL,
                enabled=True,
                capabilities={"strategic_reasoning": 1.0},
                cost_tier=CostTier.PREMIUM,
                health=ProviderHealth(status=ProviderStatus.HEALTHY, reliability_score=1.0),
            )
        )
        self.called = False

    def execute(self, task) -> ProviderResult:
        self.called = True
        return ProviderResult(provider_id=self.id, status=TaskStatus.COMPLETED)


class SequenceExecutor:
    def __init__(self, statuses: list[TaskStatus], delay_seconds: float = 0.0) -> None:
        self.statuses = list(statuses)
        self.delay_seconds = delay_seconds
        self.calls = 0

    def execute(self, tasks, decisions):
        del decisions
        if self.delay_seconds:
            sleep(self.delay_seconds)
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        task = tasks[0]
        return [
            ExecutionResult(
                task_id=task.id,
                provider_id="deterministic.tools",
                status=status,
                output={"worker_output": {"summary": "completed output", "evidence_refs": ["input"]}},
            )
        ]


class CancellingIngestor:
    def __init__(self, runtime) -> None:
        self.runtime = runtime
        self.delegate = InputIngestor()

    def ingest(self, invocation, run_id):
        manifest = self.delegate.ingest(invocation, run_id)
        self.runtime.request_cancel(run_id, "test cancellation")
        return manifest


class FailingIngestor:
    def ingest(self, invocation, run_id):
        del invocation, run_id
        raise RuntimeError("forced ingestion failure")


class TrancheDTests(unittest.TestCase):
    def test_local_only_policy_blocks_hosted_routing_even_with_key_and_internet(self) -> None:
        invocation = HostInvocation(
            prompt="Plan architecture",
            user_options=UserOptions(
                allow_internet=True,
                allow_cloud=True,
                privacy_mode=PrivacyMode.LOCAL_ONLY,
                budget_profile="premium",
            ),
        )
        manifest = InputIngestor().ingest(invocation, "run_test")
        contract = ProductContractCompiler().compile(invocation, manifest)
        policy = PolicyCompiler().compile(invocation, manifest)
        task = next(
            node
            for node in PlannerEnsemble().create_execution_plan("run_test", contract).nodes
            if node.id == "T-002"
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "placeholder"}, clear=False):
            decision = AdaptiveRouter(CapabilityRegistry.from_environment(), policy).route(task)

        self.assertFalse(policy.allow_hosted_models)
        self.assertNotEqual(decision.provider_id, "openai.configured")

    def test_internet_permission_does_not_imply_cloud_permission(self) -> None:
        invocation = HostInvocation(
            prompt="Fetch public context",
            user_options=UserOptions(allow_internet=True, privacy_mode=PrivacyMode.BALANCED),
        )
        manifest = InputIngestor().ingest(invocation, "run_test")

        policy = PolicyCompiler().compile(invocation, manifest)

        self.assertTrue(policy.allow_network_fetch)
        self.assertFalse(policy.allow_hosted_models)

    def test_executor_rechecks_policy_before_hosted_adapter_call(self) -> None:
        adapter = RecordingHostedAdapter()
        executor = DeterministicExecutor(
            adapters=ProviderAdapterRegistry([adapter]),
            execution_policy=ExecutionPolicy(
                run_id="run_test",
                privacy_mode=PrivacyMode.LOCAL_ONLY,
                allow_network_fetch=True,
                allow_hosted_models=False,
            ),
        )
        task = TaskNode(id="T-001", run_id="run_test", title="Plan", task_type=TaskType.PLANNING)
        decision = RoutingDecision(
            task_id=task.id,
            action=RoutingAction.ROUTE,
            provider_id=adapter.id,
            reason="forged route",
        )

        result = executor.execute([task], [decision])[0]

        self.assertFalse(adapter.called)
        self.assertEqual(result.status, TaskStatus.WAITING_FOR_USER)

    def test_pipeline_failure_persists_failed_state_and_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = Orchestrator(Path(tmp) / "runs")
            orchestrator.ingestor = FailingIngestor()

            with self.assertRaisesRegex(RuntimeError, "forced ingestion failure"):
                orchestrator.run(HostInvocation(prompt="Fail safely"))

            run_dir = next(path for path in (Path(tmp) / "runs").iterdir() if path.name.startswith("run_"))
            snapshot = orchestrator.runtime.resumable_snapshot(run_dir.name)

            self.assertEqual(snapshot["latest_state"], "failed")
            self.assertTrue((run_dir / "failure.json").exists())

    def test_pipeline_cancellation_cannot_reach_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = Orchestrator(Path(tmp) / "runs")
            orchestrator.ingestor = CancellingIngestor(orchestrator.runtime)

            with self.assertRaises(RunCancelledError):
                orchestrator.run(HostInvocation(prompt="Cancel safely"))

            run_dir = next(path for path in (Path(tmp) / "runs").iterdir() if path.name.startswith("run_"))
            snapshot = orchestrator.runtime.resumable_snapshot(run_dir.name)

            self.assertEqual(snapshot["latest_state"], "cancelled")
            self.assertFalse((run_dir / "run_manifest.json").exists())

    def test_scheduler_retries_failed_task(self) -> None:
        task = TaskNode(
            id="T-001",
            run_id="run_test",
            title="Retry",
            task_type=TaskType.PLANNING,
            retry_policy=RetryPolicy(max_attempts=2),
        )
        decision = RoutingDecision(
            task_id=task.id,
            action=RoutingAction.ROUTE,
            provider_id="deterministic.tools",
            reason="test",
        )
        executor = SequenceExecutor([TaskStatus.FAILED, TaskStatus.COMPLETED])

        results, report = DAGScheduler().execute(TaskDAG(run_id="run_test", nodes=[task]), [decision], executor)

        self.assertEqual(results[0].status, TaskStatus.COMPLETED)
        self.assertEqual(executor.calls, 2)
        self.assertEqual([record.attempt for record in report.records], [1, 2])

    def test_scheduler_skips_dependents_after_failure(self) -> None:
        first = TaskNode(id="T-001", run_id="run_test", title="Fail", task_type=TaskType.PLANNING)
        second = TaskNode(
            id="T-002",
            run_id="run_test",
            title="Dependent",
            task_type=TaskType.PLANNING,
            dependencies=[first.id],
        )
        decisions = [
            RoutingDecision(
                task_id=task.id,
                action=RoutingAction.ROUTE,
                provider_id="deterministic.tools",
                reason="test",
            )
            for task in [first, second]
        ]

        results, _ = DAGScheduler().execute(
            TaskDAG(run_id="run_test", nodes=[first, second]),
            decisions,
            SequenceExecutor([TaskStatus.FAILED]),
        )

        self.assertEqual(results[0].status, TaskStatus.FAILED)
        self.assertEqual(results[1].status, TaskStatus.SKIPPED)

    def test_scheduler_records_timeout(self) -> None:
        task = TaskNode(
            id="T-001",
            run_id="run_test",
            title="Timeout",
            task_type=TaskType.PLANNING,
            timeout_seconds=0,
        )
        decision = RoutingDecision(
            task_id=task.id,
            action=RoutingAction.ROUTE,
            provider_id="deterministic.tools",
            reason="test",
        )

        results, _ = DAGScheduler().execute(
            TaskDAG(run_id="run_test", nodes=[task]),
            [decision],
            SequenceExecutor([TaskStatus.COMPLETED], delay_seconds=0.05),
        )

        self.assertEqual(results[0].status, TaskStatus.FAILED)
        self.assertIn("timed out", results[0].warnings[0])

    def test_failed_run_can_resume_with_same_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = Orchestrator(Path(tmp) / "runs")
            orchestrator.ingestor = FailingIngestor()
            with self.assertRaises(RuntimeError):
                orchestrator.run(HostInvocation(prompt="Resume safely"))
            run_id = next(
                path.name for path in (Path(tmp) / "runs").iterdir() if path.name.startswith("run_")
            )

            orchestrator.ingestor = InputIngestor()
            result = orchestrator.resume(run_id)

            self.assertEqual(result.run_id, run_id)
            self.assertEqual(result.state, "delivered")

    def test_cached_repeat_run_has_no_rejected_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Stable input")
            orchestrator = Orchestrator(root / "runs")
            invocation = HostInvocation(
                prompt="Build a stable report",
                attachments=[{"uri": str(source)}],
                cwd=str(root),
            )

            orchestrator.run(invocation)
            second = orchestrator.run(invocation)
            run_dir = Path(second.artifact_dir)
            schedule = loads((run_dir / "schedule_report.json").read_text())
            package = loads((run_dir / "product_package.json").read_text())

            self.assertEqual(len(schedule["cache_hits"]), 11)
            self.assertEqual(package["rejected_fragments"], [])
            self.assertTrue(second.quality.passed)

    def test_corrupt_cache_entry_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = SemanticCache(tmp)
            key = "task_corrupt"
            (Path(tmp) / f"{key}.json").write_text("{not json")

            value = cache.get(key)

            self.assertIsNone(value)
            self.assertFalse((Path(tmp) / f"{key}.json").exists())
            self.assertTrue(list(Path(tmp).glob("task_corrupt.corrupt-*.json")))

    def test_delivery_chain_is_immutable_and_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Verifiable input\nBind every delivery artifact.")

            result = Orchestrator(root / "runs").run(
                HostInvocation(
                    prompt="Build a verifiable report",
                    attachments=[{"uri": str(source)}],
                    cwd=str(root),
                )
            )
            run_dir = Path(result.artifact_dir)
            manifest = loads((run_dir / "run_manifest.json").read_text())
            checksums = loads((run_dir / "checksums.json").read_text())
            receipt = loads((run_dir / "delivery_receipt.json").read_text())

            self.assertNotIn("run_manifest.json", [item["name"] for item in manifest["artifacts"]])
            self.assertEqual(manifest["checksums_path"], str(run_dir / "checksums.json"))
            for entry in checksums["files"]:
                path = Path(entry["path"])
                self.assertEqual(entry["content_hash"], sha256_file(path))
                self.assertEqual(entry["size_bytes"], path.stat().st_size)

            bundle = run_dir / "delivery_bundle.zip"
            self.assertEqual(receipt["bundle"]["content_hash"], sha256_file(bundle))
            self.assertEqual(
                receipt["manifest"]["content_hash"], sha256_file(run_dir / "run_manifest.json")
            )
            with zipfile.ZipFile(bundle) as archive:
                names = set(archive.namelist())
            self.assertTrue(
                {
                    "run_manifest.json",
                    "checksums.json",
                    "trace_report.json",
                    "debug_bundle_manifest.json",
                    "artifact_integrity_report.json",
                }.issubset(names)
            )

    def test_extracted_source_chunks_preserve_tail_content_and_locators(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "long-source.md"
            source.write_text(
                "# Source\n"
                + " ".join(f"evidence-{index}" for index in range(260))
                + "\nfinal-verifiable-claim"
            )
            manifest = InputIngestor().ingest(
                HostInvocation(
                    prompt="Analyze the evidence",
                    attachments=[{"uri": str(source)}],
                    cwd=str(root),
                ),
                "run_test",
            )
            context = ContextIntelligence()
            chunks = context.chunk_manifest(manifest, max_tokens=30)
            source_record = next(record for record in manifest.inputs if record.name == source.name)
            source_chunks = [chunk for chunk in chunks if chunk.input_id == source_record.id]

            self.assertNotIn("final-verifiable-claim", source_record.summary)
            self.assertIn("final-verifiable-claim", " ".join(chunk.text for chunk in source_chunks))
            self.assertGreater(len(source_chunks), 1)
            self.assertTrue(all(chunk.metadata.get("locator") for chunk in source_chunks))

    def test_pipeline_claims_resolve_to_final_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Source\nA grounded implementation requires verifiable evidence.")
            result = Orchestrator(root / "runs").run(
                HostInvocation(
                    prompt="Build a grounded implementation report",
                    attachments=[{"uri": str(source)}],
                    cwd=str(root),
                )
            )
            run_dir = Path(result.artifact_dir)
            audit = loads((run_dir / "evidence_audit.json").read_text())
            final_report = (run_dir / "final_report.md").read_text()

            self.assertTrue(audit["claims"])
            self.assertTrue(all(claim["resolved"] for claim in audit["claims"]))
            self.assertEqual(audit["invalid_evidence_refs"], [])
            self.assertNotIn("input_prompt", audit["cited_source_ids"])
            self.assertIn("## Sources", final_report)
            cited_chunks = {
                ref for claim in audit["claims"] for ref in claim["evidence_refs"]
            }
            self.assertTrue(all(f"[{ref}]" in final_report for ref in cited_chunks))

    def test_eval_gates_reject_mutated_structured_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Eval source\nValidate structured outputs, not filenames.")
            result = Orchestrator(root / "runs").run(
                HostInvocation(
                    prompt="Build an evaluated report",
                    attachments=[{"uri": str(source)}],
                    cwd=str(root),
                )
            )
            run_dir = Path(result.artifact_dir)
            runner = EvaluationRunner()

            self.assertTrue(runner._gate_passed("dag_valid", run_dir))
            dag = loads((run_dir / "task_dag.json").read_text())
            dag["nodes"][0]["dependencies"] = ["T-MISSING"]
            write_json(run_dir / "task_dag.json", dag)
            self.assertFalse(runner._gate_passed("dag_valid", run_dir))

            original_dag = result.manifest.task_dag_path
            self.assertEqual(Path(original_dag), run_dir / "task_dag.json")
            dag["nodes"][0]["dependencies"] = []
            write_json(run_dir / "task_dag.json", dag)
            decisions = loads((run_dir / "routing_decisions.json").read_text())
            write_json(run_dir / "routing_decisions.json", decisions[:-1])
            self.assertFalse(runner._gate_passed("routing_complete", run_dir))

            execution_results = loads((run_dir / "execution_results.json").read_text())
            execution_results[0]["output"]["worker_output"].pop("findings")
            write_json(run_dir / "execution_results.json", execution_results)
            self.assertFalse(runner._gate_passed("structured_outputs", run_dir))


if __name__ == "__main__":
    unittest.main()
