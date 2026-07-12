from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from universal_orchestrator.artifact_builders import ArtifactBuilder
from universal_orchestrator.models import ProductContract, SlideSpec, TaskDAG, TaskNode, TaskType
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

    def test_product_plan_validation_rejects_unknown_task_references(self) -> None:
        contract = ProductContract.model_construct(
            run_type="research_report",
            requested_output="A grounded report",
            primary_artifacts=["pdf"],
            secondary_artifacts=[],
            quality_bar="serious",
            must_have=["evidence"],
            must_not_have=[],
            definition_of_done={},
        )
        plan = PlannerEnsemble().create_product_plan("R", contract, ["T-MISSING"])
        dag = TaskDAG(
            run_id="R",
            nodes=[TaskNode(id="T-SYNTHESIS", run_id="R", title="Synthesis", task_type=TaskType.FINAL_SYNTHESIS)],
        )

        errors = PlannerEnsemble().validate_product_plan(plan, dag)

        self.assertEqual(errors, ["Product plan chapter chapter-1 references unknown task T-MISSING."])

    def test_pptx_build_and_structural_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.pptx"
            artifact = ArtifactBuilder().build_pptx(
                [SlideSpec(title="Title", body=["Evidence", "Next action"])], path
            )
            errors = ArtifactBuilder().validate_pptx(path)

        self.assertEqual(artifact.name, "report.pptx")
        self.assertEqual(errors, [])

    def test_render_validation_is_a_quality_tier_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.pdf"
            ArtifactBuilder().build_pdf("# Report\n\nGrounded content.", path)
            builder = ArtifactBuilder()
            builder._render_first_page = lambda kind, artifact: (None, "fixture renderer unavailable")

            serious_errors, serious_warnings = builder.validate_rendered("pdf", path, "serious")
            standard_errors, standard_warnings = builder.validate_rendered("pdf", path, "standard")

        self.assertTrue(serious_errors)
        self.assertEqual(serious_warnings, [])
        self.assertEqual(standard_errors, [])
        self.assertTrue(standard_warnings)

    def test_render_validation_inspects_every_page_and_cleans_temp_output(self) -> None:
        from reportlab.pdfgen import canvas
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "two-pages.pdf"
            document = canvas.Canvas(str(path))
            document.drawString(72, 720, "Visible first page")
            document.showPage()
            document.showPage()
            document.save()

            render_dir = root / "rendered"
            render_dir.mkdir()
            first_page = render_dir / "page-1.png"
            second_page = render_dir / "page-2.png"
            first_image = Image.new("RGB", (400, 300), "white")
            ImageDraw.Draw(first_image).rectangle((20, 20, 200, 120), fill="black")
            first_image.save(first_page)
            Image.new("RGB", (400, 300), "white").save(second_page)

            builder = ArtifactBuilder()
            with patch.object(
                builder,
                "_render_first_page",
                return_value=(first_page, None),
            ):
                errors, warnings = builder.validate_rendered("pdf", path, "serious")

            self.assertTrue(any("page 2" in error for error in errors))
            self.assertEqual(warnings, [])
            self.assertFalse(render_dir.exists())


if __name__ == "__main__":
    unittest.main()
