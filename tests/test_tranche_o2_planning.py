from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from universal_orchestrator.artifact_builders import ArtifactBuilder
from universal_orchestrator.execution import DeterministicExecutor
from universal_orchestrator.models import (
    ContextChunk,
    ProductContract,
    ProductPlan,
    RepoValidationReport,
    RoutingAction,
    RoutingDecision,
    TaskDAG,
    TaskNode,
    TaskStatus,
    TaskType,
)
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.stages import KernelStageContext, StageWorkerRegistry


def contract(run_type: str) -> ProductContract:
    return ProductContract.model_construct(
        run_type=run_type,
        requested_output=f"Deliver a {run_type} product",
        primary_artifacts=["final_report"],
        secondary_artifacts=[],
        quality_bar="serious",
        must_have=[],
        must_not_have=[],
        definition_of_done={},
    )


class TrancheO2PlanningTests(unittest.TestCase):
    def test_each_product_family_has_executable_acceptance_contract(self) -> None:
        planner = PlannerEnsemble()
        for run_type in (
            "research_report",
            "repo_implementation",
            "code_review",
            "orchestrated_task",
        ):
            with self.subTest(run_type=run_type):
                plan = planner.create_product_plan(
                    "R",
                    contract(run_type),
                    ["T-SYNTHESIS", "T-CHAPTER-002", "T-CHAPTER-003"],
                )

                self.assertEqual(plan.run_type, run_type)
                self.assertTrue(plan.execution_steps)
                self.assertTrue(plan.acceptance_criteria)
                self.assertTrue(plan.required_artifacts)
                self.assertTrue(any("validat" in step.lower() for step in plan.execution_steps))

    def test_product_plan_validation_rejects_missing_executable_contract(self) -> None:
        planner = PlannerEnsemble()
        broken = ProductPlan(
            run_id="R",
            title="Incomplete plan",
            chapters=[],
            artifact_types=["final_report"],
        )
        dag = TaskDAG(
            run_id="R",
            nodes=[
                TaskNode(
                    id="T-SYNTHESIS",
                    run_id="R",
                    title="Synthesis",
                    task_type=TaskType.FINAL_SYNTHESIS,
                )
            ],
        )

        errors = planner.validate_product_plan(broken, dag)

        self.assertIn("Product plan has no executable steps.", errors)
        self.assertIn("Product plan has no acceptance criteria.", errors)
        self.assertIn("Product plan has no required artifacts.", errors)

    def test_repository_patch_plan_contains_product_specific_execution_contract(self) -> None:
        plan = PlannerEnsemble().create_product_plan(
            "R",
            contract("repo_implementation"),
            ["T-SYNTHESIS", "T-CHAPTER-002", "T-CHAPTER-003"],
        )
        validation = RepoValidationReport(
            run_id="R",
            executed=False,
            passed=True,
            warnings=["allow_shell is false; validation was planned but not executed."],
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "patch_plan.md"
            ArtifactBuilder().build_patch_plan(
                "# Final report\n\nRepository findings.",
                path,
                product_plan=plan,
                repo_validation_report=validation,
            )
            text = path.read_text()

        self.assertIn("## Execution Steps", text)
        self.assertIn("## Acceptance Criteria", text)
        self.assertIn("## Validation Status", text)
        self.assertIn("not an implementation patch", text)
        self.assertIn("validation was planned", text)

    def test_reshape_executes_bounded_local_fallback(self) -> None:
        chunk = ContextChunk(
            id="chunk-source",
            input_id="input-source",
            ordinal=0,
            text="The local fallback preserves the delivered source evidence.",
            token_estimate=10,
            content_hash="hash-source",
        )
        task = TaskNode(
            id="T-CHAPTER-002",
            run_id="R",
            title="Findings",
            task_type=TaskType.FINAL_SYNTHESIS,
            chapter_id="chapter-2",
            chapter_title="Findings And Evidence",
            objective="Report validated findings.",
        )
        context = KernelStageContext(
            manifest=SimpleNamespace(inputs=[]),
            contract=contract("research_report"),
            cards=[],
            chunks=[chunk],
            conflicts=[],
            chunk_refs_by_task={task.id: [chunk.id]},
            build_static_artifacts=lambda: [],
            evaluate_quality=lambda results: SimpleNamespace(),
        )
        result = StageWorkerRegistry(context).execute(
            [task],
            [
                RoutingDecision(
                    task_id=task.id,
                    action=RoutingAction.RESHAPE,
                    reason="No premium model is available; use the bounded local form.",
                )
            ],
        )[0]

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(result.output["worker_output"]["synthesis_path"], "extractive_reshape")
        self.assertTrue(any("reshaped" in warning.lower() for warning in result.warnings))

    def test_legacy_executor_also_completes_reshape_locally(self) -> None:
        task = TaskNode(
            id="T-LEGACY-RESHAPE",
            run_id="R",
            title="Local reshape",
            task_type=TaskType.PLANNING,
        )
        result = DeterministicExecutor().execute(
            [task],
            [
                RoutingDecision(
                    task_id=task.id,
                    action=RoutingAction.RESHAPE,
                    reason="No strategic provider is configured.",
                )
            ],
        )[0]

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(result.provider_id, "deterministic.tools")
        self.assertEqual(result.output["worker_output"]["synthesis_path"], "deterministic_reshape")


if __name__ == "__main__":
    unittest.main()
