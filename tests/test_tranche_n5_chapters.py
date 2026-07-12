from __future__ import annotations

import unittest
from types import SimpleNamespace

from universal_orchestrator.model_synthesis import ModelSynthesisRunner
from universal_orchestrator.models import (
    ContextChunk,
    ProductContract,
    RoutingAction,
    RoutingDecision,
    TaskNode,
    TaskType,
)
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.stages import KernelStageContext, StageWorkerRegistry


def contract(run_type: str, requested_output: str = "Deliver the requested product") -> ProductContract:
    return ProductContract.model_construct(
        run_type=run_type,
        requested_output=requested_output,
        primary_artifacts=["pdf"],
        secondary_artifacts=[],
        quality_bar="serious",
        must_have=[],
        must_not_have=[],
        definition_of_done={},
    )


class TrancheN5ChapterTests(unittest.TestCase):
    def test_chapter_contracts_are_run_type_specific_and_distinct(self) -> None:
        planner = PlannerEnsemble()
        expected = {
            "research_report": [
                "Executive Summary",
                "Findings And Evidence",
                "Risks And Recommendations",
            ],
            "repo_implementation": [
                "System Overview",
                "Engineering Findings",
                "Implementation And Validation",
            ],
            "orchestrated_task": [
                "Objective And Context",
                "Results And Evidence",
                "Risks And Next Actions",
            ],
        }

        for run_type, titles in expected.items():
            with self.subTest(run_type=run_type):
                plan = planner.create_product_plan(
                    "R",
                    contract(run_type),
                    ["T-SYNTHESIS", "T-CHAPTER-002", "T-CHAPTER-003"],
                )
                self.assertEqual([chapter.title for chapter in plan.chapters], titles)
                self.assertEqual(
                    len({chapter.objective for chapter in plan.chapters}),
                    3,
                )

    def test_execution_nodes_carry_chapter_metadata_and_final_build_depends_on_all(self) -> None:
        planner = PlannerEnsemble()
        dag = planner.create_execution_plan("R", contract("repo_implementation"))
        chapters = [node for node in dag.nodes if node.chapter_id]

        self.assertEqual([node.chapter_id for node in chapters], ["chapter-1", "chapter-2", "chapter-3"])
        self.assertEqual(
            [node.chapter_title for node in chapters],
            ["System Overview", "Engineering Findings", "Implementation And Validation"],
        )
        self.assertEqual(len({node.objective for node in chapters}), 3)
        build = next(node for node in dag.nodes if node.id == "T-ARTIFACT-BUILD")
        self.assertEqual(
            build.dependencies,
            ["T-SYNTHESIS", "T-CHAPTER-002", "T-CHAPTER-003"],
        )

    def test_extractive_chapters_have_different_deterministic_outputs(self) -> None:
        chunk = ContextChunk(
            id="chunk-1",
            input_id="input-1",
            ordinal=0,
            text="The deployment has a documented validation command.",
            token_estimate=8,
            content_hash="hash-1",
        )
        context = KernelStageContext(
            manifest=SimpleNamespace(inputs=[], conflicts=[]),
            contract=contract("repo_implementation"),
            cards=[],
            chunks=[chunk],
            conflicts=["The deployment command is missing from one environment."],
            chunk_refs_by_task={"T-CHAPTER-002": [chunk.id], "T-CHAPTER-003": [chunk.id]},
            build_static_artifacts=lambda: [],
            evaluate_quality=lambda results: SimpleNamespace(),
        )
        worker = StageWorkerRegistry(context)
        def decision(task_id: str) -> RoutingDecision:
            return RoutingDecision(
                task_id=task_id,
                action=RoutingAction.ROUTE,
                provider_id="deterministic.tools",
                reason="fixture",
            )
        findings_task = TaskNode(
            id="T-CHAPTER-002",
            run_id="R",
            title="Engineering Findings",
            task_type=TaskType.FINAL_SYNTHESIS,
            chapter_id="chapter-2",
            chapter_title="Engineering Findings",
            objective="Describe validated engineering findings.",
        )
        risks_task = findings_task.model_copy(
            update={
                "id": "T-CHAPTER-003",
                "title": "Implementation And Validation",
                "chapter_id": "chapter-3",
                "chapter_title": "Implementation And Validation",
                "objective": "Describe risks and validation next actions.",
            }
        )

        findings = worker.execute([findings_task], [decision(findings_task.id)])[0]
        risks = worker.execute([risks_task], [decision(risks_task.id)])[0]

        self.assertNotEqual(
            findings.output["worker_output"]["summary"],
            risks.output["worker_output"]["summary"],
        )
        self.assertEqual(
            findings.output["worker_output"]["chapter_id"],
            "chapter-2",
        )
        self.assertEqual(
            risks.output["worker_output"]["chapter_id"],
            "chapter-3",
        )

    def test_model_prompt_contains_chapter_title_and_objective(self) -> None:
        task = TaskNode(
            id="T-CHAPTER-002",
            run_id="R",
            title="Engineering Findings",
            task_type=TaskType.FINAL_SYNTHESIS,
            chapter_id="chapter-2",
            chapter_title="Engineering Findings",
            objective="Describe validated engineering findings.",
        )

        prompt = ModelSynthesisRunner()._initial_prompt("Operator request", task)

        self.assertIn("Engineering Findings", prompt)
        self.assertIn("Describe validated engineering findings.", prompt)


if __name__ == "__main__":
    unittest.main()
