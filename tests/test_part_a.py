import tempfile
import unittest
import zipfile
from pathlib import Path

from universal_orchestrator.cache import SemanticCache
from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.execution import DeterministicExecutor
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.ingestion.hardening import detect_text_encoding
from universal_orchestrator.models import HostInvocation, InputAttachment, RuntimeEvent
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.repo import RepoAnalyzer
from universal_orchestrator.routing import AdaptiveRouter, CapabilityRegistry
from universal_orchestrator.runtime import RuntimeStore
from universal_orchestrator.scheduler import DAGScheduler


class PartAGapTests(unittest.TestCase):
    def test_scheduler_batches_and_records_execution(self) -> None:
        invocation = HostInvocation(prompt="Schedule this work")
        manifest = InputIngestor().ingest(invocation, "run_test")
        contract = ProductContractCompiler().compile(invocation, manifest)
        dag = PlannerEnsemble().create_execution_plan("run_test", contract)
        registry = CapabilityRegistry.from_environment()
        decisions = AdaptiveRouter(registry).route_all(dag.topological_order())
        executor = DeterministicExecutor(adapters=registry.adapter_registry(), prompt=invocation.prompt)

        with tempfile.TemporaryDirectory() as tmp:
            results, report = DAGScheduler(SemanticCache(tmp)).execute(dag, decisions, executor)

        self.assertEqual(len(results), len(dag.nodes))
        self.assertGreater(len(report.parallel_batches), 1)
        self.assertEqual(report.failed_tasks, [])

    def test_runtime_store_tracks_transitions_and_task_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RuntimeStore(Path(tmp) / "runtime.sqlite3")
            store.record_event(RuntimeEvent(run_id="run_test", event_type="received"))
            store.transition("run_test", "executing")
            store.save_task_record("run_test", "T-001", "completed", 1, "cache-key")

            snapshot = store.resumable_snapshot("run_test")

        self.assertEqual(snapshot["latest_state"], "executing")
        self.assertEqual(snapshot["tasks"][0]["task_id"], "T-001")

    def test_plan_review_includes_simulation_and_critical_path(self) -> None:
        invocation = HostInvocation(prompt="Plan deeply")
        manifest = InputIngestor().ingest(invocation, "run_test")
        contract = ProductContractCompiler().compile(invocation, manifest)
        planner = PlannerEnsemble()
        dag = planner.create_execution_plan("run_test", contract)

        review = planner.review_plan("run_test", contract, dag)

        self.assertTrue(review.critical_path)
        self.assertGreater(review.simulation["max_parallelism"], 0)
        self.assertEqual(review.simulation["task_count"], len(dag.nodes))

    def test_context_chunks_provenance_and_packs(self) -> None:
        invocation = HostInvocation(prompt="Use context")
        manifest = InputIngestor().ingest(invocation, "run_test")
        context = ContextIntelligence()
        cards = context.build_cards(manifest)
        chunks = context.chunk_manifest(manifest)
        provenance = context.provenance(cards, chunks)
        packs = context.compile_packs_for_tasks(["T-001", "T-002"], cards, token_budget=100)

        self.assertTrue(chunks)
        self.assertEqual(len(provenance), len(cards))
        self.assertEqual(set(packs), {"T-001", "T-002"})

    def test_repo_analyzer_detects_python_project(self) -> None:
        repo = RepoAnalyzer().analyze(Path.cwd())

        self.assertIn("python", repo.frameworks)
        self.assertIn("PYTHONPATH=src python -m unittest discover -s tests", repo.test_commands)

    def test_ingestion_hardening_detects_encoding_and_archive_limits(self) -> None:
        self.assertEqual(detect_text_encoding("hello".encode("utf-16")), "utf-16")
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "many.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for index in range(3):
                    archive.writestr(f"file-{index}.txt", "x")
            ingestor = InputIngestor()
            ingestor.limits.max_archive_entries = 1
            manifest = ingestor.ingest(
                HostInvocation(prompt="Inspect archive", attachments=[InputAttachment(uri=str(archive_path))]),
                "run_test",
            )

        record = next(item for item in manifest.inputs if item.name == "many.zip")
        self.assertTrue(any("max entries" in warning for warning in record.warnings))

    def test_ingestion_limits_are_read_through(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(3):
                (root / f"file-{index}.txt").write_text("x")

            ingestor = InputIngestor()
            ingestor.limits.max_folder_files = 1
            manifest = ingestor.ingest(
                HostInvocation(prompt="Inspect folder", attachments=[InputAttachment(uri=str(root))]),
                "run_test",
            )

        record = next(item for item in manifest.inputs if item.path == str(root.resolve()))
        self.assertEqual(record.metadata["files_scanned"], 1)
        self.assertTrue(any("capped" in warning for warning in record.warnings))


if __name__ == "__main__":
    unittest.main()
