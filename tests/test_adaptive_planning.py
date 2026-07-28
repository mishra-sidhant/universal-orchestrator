from __future__ import annotations

import unittest

from universal_orchestrator.models import DefinitionOfDone, ProductContract
from universal_orchestrator.planning import PlannerEnsemble


class AdaptivePlanningTests(unittest.TestCase):
    def test_default_blueprint_preserves_three_stable_task_ids(self) -> None:
        contract = ProductContract(
            run_type="research_report",
            requested_output="Produce a grounded report",
            primary_artifacts=["report"],
            must_have=[],
            must_not_have=[],
            definition_of_done=DefinitionOfDone(gates=["evidence"]),
        )
        planner = PlannerEnsemble()

        blueprint = planner.create_blueprint("run-default", contract)
        dag = planner.create_execution_plan("run-default", contract)

        self.assertEqual([unit.task_id for unit in blueprint.work_units], [
            "T-SYNTHESIS", "T-CHAPTER-002", "T-CHAPTER-003"
        ])
        self.assertEqual(len(dag.nodes), 7)

    def test_requested_sections_compile_to_bounded_parallel_work_units(self) -> None:
        contract = ProductContract(
            run_type="orchestrated_task",
            requested_output="Produce a package",
            primary_artifacts=["report"],
            must_have=[],
            must_not_have=[],
            constraints={
                "sections": [
                    {"title": "Context", "objective": "Explain context."},
                    "Findings",
                    "Risks",
                    "Actions",
                ]
            },
            definition_of_done=DefinitionOfDone(gates=["delivery"]),
        )
        planner = PlannerEnsemble()

        blueprint = planner.create_blueprint("run-adaptive", contract, max_parallel_tasks=3)
        dag = planner.create_execution_plan("run-adaptive", contract)
        chapter_nodes = [node for node in dag.nodes if node.task_type == "final_synthesis"]

        self.assertEqual(len(blueprint.work_units), 4)
        self.assertEqual(blueprint.max_parallel_tasks, 3)
        self.assertEqual(len(chapter_nodes), 4)
        self.assertEqual(
            [node.id for node in chapter_nodes],
            ["T-SYNTHESIS", "T-CHAPTER-002", "T-CHAPTER-003", "T-CHAPTER-004"],
        )
        artifact = next(node for node in dag.nodes if node.id == "T-ARTIFACT-BUILD")
        self.assertEqual(artifact.dependencies, [node.id for node in chapter_nodes])

    def test_section_count_is_capped_without_silent_empty_nodes(self) -> None:
        contract = ProductContract(
            run_type="orchestrated_task",
            requested_output="Produce a package",
            primary_artifacts=["report"],
            must_have=[],
            must_not_have=[],
            constraints={"sections": [f"Section {index}" for index in range(30)]},
            definition_of_done=DefinitionOfDone(gates=["delivery"]),
        )

        blueprint = PlannerEnsemble().create_blueprint("run-capped", contract)

        self.assertEqual(len(blueprint.work_units), 12)
        self.assertTrue(all(unit.title and unit.objective for unit in blueprint.work_units))


if __name__ == "__main__":
    unittest.main()
