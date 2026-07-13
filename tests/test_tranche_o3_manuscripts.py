from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from universal_orchestrator.model_synthesis import ModelOutputValidationError, ModelSynthesisRunner
from universal_orchestrator.models import (
    ContextChunk,
    ProductContract,
    RoutingAction,
    RoutingDecision,
    TaskNode,
    TaskType,
)
from universal_orchestrator.product import FinalProductOwner
from universal_orchestrator.stages import KernelStageContext, StageWorkerRegistry


def contract() -> ProductContract:
    return ProductContract.model_construct(
        run_type="research_report",
        requested_output="Deliver a grounded report",
        primary_artifacts=["final_report"],
        secondary_artifacts=[],
        quality_bar="serious",
        must_have=[],
        must_not_have=[],
        definition_of_done={},
    )


class TrancheO3ManuscriptTests(unittest.TestCase):
    def test_model_schema_rejects_output_without_structured_manuscript(self) -> None:
        runner = ModelSynthesisRunner()
        raw = json.dumps(
            {
                "summary": "A grounded summary.",
                "findings": [],
                "claims": [{"text": "A claim.", "evidence_refs": ["chunk-1"]}],
            }
        )

        with self.assertRaises(ModelOutputValidationError):
            runner._parse(raw)

    def test_model_prompt_requires_objective_specific_manuscript(self) -> None:
        task = TaskNode(
            id="T-CHAPTER-002",
            run_id="R",
            title="Findings",
            task_type=TaskType.FINAL_SYNTHESIS,
            chapter_title="Findings And Evidence",
            objective="Tie findings to delivered evidence.",
        )

        prompt = ModelSynthesisRunner()._initial_prompt("Answer the operator", task)

        self.assertIn("manuscript", prompt.lower())
        self.assertIn("heading", prompt.lower())
        self.assertIn("body", prompt.lower())
        self.assertIn("objective", prompt.lower())

    def test_extractive_path_emits_structured_manuscript(self) -> None:
        chunk = ContextChunk(
            id="chunk-1",
            input_id="input-1",
            ordinal=0,
            text="The evidence supports a bounded local execution path.",
            token_estimate=10,
            content_hash="hash-1",
        )
        task = TaskNode(
            id="T-CHAPTER-003",
            run_id="R",
            title="Risks",
            task_type=TaskType.FINAL_SYNTHESIS,
            chapter_id="chapter-3",
            chapter_title="Risks And Recommendations",
            objective="Describe risks and recommendations.",
        )
        context = KernelStageContext(
            manifest=SimpleNamespace(inputs=[]),
            contract=contract(),
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
                    action=RoutingAction.ROUTE,
                    provider_id="deterministic.tools",
                    reason="fixture",
                )
            ],
        )[0]

        manuscript = result.output["worker_output"]["manuscript"]
        self.assertEqual(len(manuscript), 1)
        self.assertEqual(manuscript[0]["heading"], "Risks And Recommendations")
        self.assertEqual(manuscript[0]["objective"], task.objective)
        self.assertIn("bounded local", manuscript[0]["body"])
        self.assertEqual(manuscript[0]["evidence_refs"], [chunk.id])

    def test_product_owner_renders_manuscript_sections(self) -> None:
        task = TaskNode(
            id="T-SYNTHESIS",
            run_id="R",
            title="Synthesis",
            task_type=TaskType.FINAL_SYNTHESIS,
            chapter_id="chapter-1",
            chapter_title="Executive Summary",
            objective="Answer the request.",
        )
        result = SimpleNamespace(
            task_id=task.id,
            status="completed",
            warnings=[],
            output={
                "worker_output": {
                    "summary": "Short summary.",
                    "manuscript": [
                        {
                            "heading": "Executive Summary",
                            "objective": "Answer the request.",
                            "body": "A structured manuscript body.",
                            "evidence_refs": [],
                        }
                    ],
                }
            },
        )
        quality = SimpleNamespace(
            warnings=[],
            violations=[],
            scores=SimpleNamespace(
                completeness=100,
                parse_confidence=100,
                citation_support=100,
                continuity=100,
                routing_efficiency=100,
                artifact_presence="pass",
                code_validation="not_applicable",
            ),
        )
        package = FinalProductOwner().assemble(
            SimpleNamespace(run_id="R", inputs=[], parsed_count=0),
            contract(),
            [],
            SimpleNamespace(nodes=[task]),
            [],
            [result],
            quality,
        )

        self.assertIn("A structured manuscript body.", package.final_markdown)
        self.assertIn("Section objective: Answer the request.", package.final_markdown)


if __name__ == "__main__":
    unittest.main()
