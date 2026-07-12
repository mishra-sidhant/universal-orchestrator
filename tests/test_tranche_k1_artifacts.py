from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from universal_orchestrator.artifact_builders import ArtifactBuilder
from universal_orchestrator.models import ProductContract, SlideSpec
from universal_orchestrator.planning import PlannerEnsemble


class ArtifactAndProductPlanTests(unittest.TestCase):
    def test_product_plan_is_typed_and_deterministic(self) -> None:
        contract = ProductContract.model_construct(
            run_type="research_report",
            requested_output="A grounded report",
            primary_artifacts=["pptx"],
            secondary_artifacts=[],
            quality_bar="serious",
            must_have=["evidence"],
            must_not_have=[],
            definition_of_done={},
        )
        plan = PlannerEnsemble().create_product_plan("R", contract, ["T-SYNTHESIS"])

        self.assertEqual(plan.chapters[0].task_ids, ["T-SYNTHESIS"])

    def test_pptx_build_and_structural_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.pptx"
            artifact = ArtifactBuilder().build_pptx(
                [SlideSpec(title="Title", body=["Evidence", "Next action"])], path
            )
            errors = ArtifactBuilder().validate_pptx(path)

        self.assertEqual(artifact.name, "report.pptx")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
