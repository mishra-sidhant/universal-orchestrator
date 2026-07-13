from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from universal_orchestrator.artifact_builders import ArtifactBuilder
from universal_orchestrator.evidence import EvidenceAuditor
from universal_orchestrator.models import (
    ClaimVerification,
    ClaimVerificationStatus,
    HostInvocation,
    InputAttachment,
    ProductContract,
    RunState,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.planning import PlannerEnsemble


class InsufficientVerifier:
    def verify(
        self,
        claim_text: str,
        evidence_refs: list[str],
        chunks: list[object],
    ) -> ClaimVerification:
        del chunks
        return ClaimVerification(
            claim_text=claim_text,
            evidence_refs=evidence_refs,
            status=ClaimVerificationStatus.INSUFFICIENT,
            method="fixture_insufficient",
            warning="fixture evidence is insufficient",
        )


class TrancheO0BoundaryTests(unittest.TestCase):
    def _source_invocation(self, source: Path) -> HostInvocation:
        return HostInvocation(
            prompt="Build a grounded report",
            attachments=[InputAttachment(uri=str(source))],
        )

    def test_insufficient_verification_blocks_delivery_and_citation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.md"
            source.write_text("The source contains a bounded execution claim.")
            orchestrator = Orchestrator(root / "runs")
            orchestrator.evidence = EvidenceAuditor(InsufficientVerifier())

            result = orchestrator.run(self._source_invocation(source))
            audit = json.loads(
                (Path(result.artifact_dir) / "evidence_audit.json").read_text()
            )

        self.assertEqual(result.state, RunState.NEEDS_ATTENTION)
        self.assertTrue(audit["claims"])
        self.assertTrue(
            all(
                claim["verification"]["status"] == ClaimVerificationStatus.INSUFFICIENT
                and not claim["citation_eligible"]
                for claim in audit["claims"]
                if claim["evidence_required"]
            )
        )

    def test_late_zip_demotion_updates_the_human_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            orchestrator = Orchestrator(root / "runs")
            with patch.object(
                orchestrator.artifact_builder,
                "validate_zip",
                return_value=["forced zip corruption"],
            ):
                result = orchestrator.run(HostInvocation(prompt="Produce a final report"))

            report = (Path(result.artifact_dir) / "final_report.md").read_text()

        self.assertEqual(result.state, RunState.NEEDS_ATTENTION)
        self.assertNotIn("Quality passed: `True`", report)
        self.assertIn("quality_report.json", report)

    def test_zip_construction_failure_is_an_honest_needs_attention_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            orchestrator = Orchestrator(root / "runs")
            with patch.object(
                orchestrator.artifact_builder,
                "build_zip",
                side_effect=OSError("disk full"),
            ):
                result = orchestrator.run(HostInvocation(prompt="Produce a final report"))

            run_dir = Path(result.artifact_dir)
            manifest = json.loads((run_dir / "run_manifest.json").read_text())

        self.assertEqual(result.state, RunState.NEEDS_ATTENTION)
        self.assertEqual(manifest["state"], RunState.NEEDS_ATTENTION)
        self.assertIsNone(manifest["delivery_receipt_path"])
        self.assertFalse((run_dir / "delivery_receipt.json").exists())

    def test_render_validation_rejects_missing_source_pages(self) -> None:
        from PIL import Image, ImageDraw
        from reportlab.pdfgen import canvas

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "two-pages.pdf"
            document = canvas.Canvas(str(pdf_path))
            document.drawString(72, 720, "Page one")
            document.showPage()
            document.drawString(72, 720, "Page two")
            document.showPage()
            document.save()

            render_dir = root / "rendered"
            render_dir.mkdir()
            first_page = render_dir / "page-1.png"
            image = Image.new("RGB", (400, 300), "white")
            ImageDraw.Draw(image).rectangle((20, 20, 200, 120), fill="black")
            image.save(first_page)

            builder = ArtifactBuilder()
            with patch.object(
                builder,
                "_render_first_page",
                return_value=(first_page, None),
            ):
                errors, warnings = builder.validate_rendered("pdf", pdf_path, "serious")

        self.assertTrue(any("expected 2 rendered pages" in error for error in errors))
        self.assertEqual(warnings, [])

    def test_render_timeout_is_a_quality_result_and_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "report.pdf"
            ArtifactBuilder().build_pdf("# Report\n\nVisible content.", pdf_path)
            render_dir = root / "rendered"
            with (
                patch(
                    "universal_orchestrator.artifact_builders.shutil.which",
                    return_value="pdftoppm",
                ),
                patch(
                    "universal_orchestrator.artifact_builders.tempfile.mkdtemp",
                    return_value=str(render_dir),
                ),
                patch(
                    "universal_orchestrator.artifact_builders.subprocess.run",
                    side_effect=subprocess.TimeoutExpired("pdftoppm", 30),
                ),
            ):
                errors, warnings = ArtifactBuilder().validate_rendered(
                    "pdf", pdf_path, "serious"
                )

        self.assertTrue(errors)
        self.assertEqual(warnings, [])
        self.assertFalse(render_dir.exists())

    def test_model_enabled_plans_route_all_chapters_to_model_capability(self) -> None:
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
        dag = PlannerEnsemble().create_execution_plan(
            "run_test", contract, model_synthesis=True
        )

        chapter_nodes = [node for node in dag.nodes if node.chapter_id]

        self.assertEqual(len(chapter_nodes), 3)
        self.assertTrue(
            all(node.required_capabilities.get("final_synthesis", 0.0) >= 0.6 for node in chapter_nodes)
        )


if __name__ == "__main__":
    unittest.main()
