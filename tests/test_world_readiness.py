import tempfile
import unittest
from pathlib import Path

from universal_orchestrator.artifact_builders import ArtifactBuilder
from universal_orchestrator.cache import SemanticCache
from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.evals import built_in_suite
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import HostInvocation, RuntimeEvent
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.policy import SecurityPolicy
from universal_orchestrator.product import FinalProductOwner
from universal_orchestrator.runtime import RuntimeStore


class WorldReadinessTests(unittest.TestCase):
    def test_planner_review_scores_candidate_roles(self) -> None:
        invocation = HostInvocation(prompt="Build a product package", attachments=[])
        manifest = InputIngestor().ingest(invocation, "run_test")
        contract = ProductContractCompiler().compile(invocation, manifest)
        planner = PlannerEnsemble()
        dag = planner.create_execution_plan("run_test", contract)

        review = planner.review_plan("run_test", contract, dag)

        self.assertGreaterEqual(len(review.candidates), 5)
        self.assertGreater(review.score, 0.7)
        self.assertIn("T-AGGREGATE", review.selected_task_ids)

    def test_context_index_and_cache(self) -> None:
        invocation = HostInvocation(prompt="Analyze alpha", attachments=[])
        manifest = InputIngestor().ingest(invocation, "run_test")
        context = ContextIntelligence()
        cards = context.build_cards(manifest)
        index = context.build_index(cards)

        with tempfile.TemporaryDirectory() as tmp:
            cache = SemanticCache(tmp)
            key = cache.key_for("cards", {"count": len(cards)})
            cache.set(key, {"terms": len(index)})

            self.assertEqual(cache.get(key)["terms"], len(index))
        self.assertTrue(index)

    def test_artifact_builder_creates_valid_pdf_and_docx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            builder = ArtifactBuilder()
            pdf = root / "out.pdf"
            docx = root / "out.docx"

            builder.build_pdf("# Title\n\nBody text", pdf)
            builder.build_docx("# Title\n\nBody text", docx)

            self.assertEqual(builder.validate_pdf(pdf), [])
            self.assertEqual(builder.validate_docx(docx), [])

    def test_security_policy_and_runtime_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = SecurityPolicy(root)
            store = RuntimeStore(root / "runtime.sqlite3")
            store.record_event(RuntimeEvent(run_id="run_test", event_type="received"))

            self.assertTrue(policy.is_path_inside_workspace(root / "file.txt"))
            self.assertFalse(policy.is_archive_member_safe("../bad.txt"))
            self.assertFalse(policy.is_url_allowed("https://example.com", allow_internet=False))
            self.assertEqual(store.list_events("run_test")[0]["event_type"], "received")

    def test_eval_suite_describes_world_readiness_cases(self) -> None:
        suite = built_in_suite()

        self.assertEqual(suite.name, "world_readiness_core")
        self.assertGreaterEqual(len(suite.cases), 3)

    def test_final_product_owner_builds_final_markdown(self) -> None:
        invocation = HostInvocation(prompt="Build final product")
        manifest = InputIngestor().ingest(invocation, "run_test")
        contract = ProductContractCompiler().compile(invocation, manifest)
        dag = PlannerEnsemble().create_execution_plan("run_test", contract)
        package = FinalProductOwner().assemble(
            manifest=manifest,
            contract=contract,
            cards=ContextIntelligence().build_cards(manifest),
            dag=dag,
            decisions=[],
            results=[],
            quality=_passing_quality(),
        )

        self.assertIn("Universal Orchestrator Final Product", package.final_markdown)


def _passing_quality():
    from universal_orchestrator.models import QualityGateResult, QualityScore

    return QualityGateResult(
        passed=True,
        scores=QualityScore(
            completeness=90,
            parse_confidence=90,
            citation_support=90,
            continuity=90,
            routing_efficiency=90,
            artifact_presence="pass",
            code_validation="not_applicable",
        ),
    )


if __name__ == "__main__":
    unittest.main()
