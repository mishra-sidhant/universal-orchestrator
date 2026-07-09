import tempfile
import unittest
from pathlib import Path

from universal_orchestrator.models import HostInvocation, InputAttachment
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.routing import CapabilityRegistry


class PipelineTests(unittest.TestCase):
    def test_pipeline_writes_product_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Product\nBuild the kernel spine.")
            out = root / "runs"
            invocation = HostInvocation(
                prompt="Build a serious implementation report from this source",
                attachments=[InputAttachment(uri=str(source))],
                cwd=str(root),
            )

            result = Orchestrator(out).run(invocation)

            run_dir = Path(result.artifact_dir)
            self.assertTrue(result.quality.passed)
            self.assertIsNotNone(result.manifest.completed_at)
            self.assertGreaterEqual(result.manifest.completed_at, result.manifest.started_at)
            self.assertTrue((run_dir / "run_manifest.json").exists())
            self.assertTrue((run_dir / "final_report.md").exists())
            self.assertTrue((run_dir / "context_manifest.json").exists())
            self.assertTrue((run_dir / "plan_review.json").exists())
            self.assertTrue((run_dir / "product_package.json").exists())
            self.assertTrue((run_dir / "validation_findings.json").exists())
            execution_results = (run_dir / "execution_results.json").read_text()
            self.assertIn("worker_output", execution_results)
            self.assertIn("findings", execution_results)

    def test_pipeline_builds_requested_pdf_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Product\nBuild the kernel spine.")
            out = root / "runs"
            invocation = HostInvocation(
                prompt="Build a serious implementation report as pdf",
                attachments=[InputAttachment(uri=str(source))],
                cwd=str(root),
            )

            result = Orchestrator(out).run(invocation)

            run_dir = Path(result.artifact_dir)
            self.assertTrue(result.quality.passed)
            self.assertTrue((run_dir / "final_report.pdf").exists())
            self.assertTrue((run_dir / "pdf_validation.json").exists())

    def test_deterministic_registry_can_degrade_core_reasoning_tasks(self) -> None:
        capabilities = CapabilityRegistry.from_environment().providers[0].capabilities

        self.assertGreater(capabilities["strategic_reasoning"], 0)
        self.assertGreater(capabilities["final_synthesis"], 0)
        self.assertGreater(capabilities["code_reasoning"], 0)


if __name__ == "__main__":
    unittest.main()
