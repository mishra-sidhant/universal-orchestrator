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
            self.assertTrue((run_dir / "context_chunks.json").exists())
            self.assertTrue((run_dir / "context_provenance.json").exists())
            self.assertTrue((run_dir / "context_packs.json").exists())
            self.assertTrue((run_dir / "plan_review.json").exists())
            self.assertTrue((run_dir / "product_plan.json").exists())
            self.assertTrue((run_dir / "product_plan_validation.json").exists())
            self.assertTrue((run_dir / "approval_report.json").exists())
            self.assertTrue((run_dir / "policy_report.json").exists())
            self.assertTrue((run_dir / "budget_report.json").exists())
            self.assertTrue((run_dir / "delta_execution_plan.json").exists())
            self.assertTrue((run_dir / "product_package.json").exists())
            self.assertTrue((run_dir / "validation_findings.json").exists())
            self.assertTrue((run_dir / "evidence_audit.json").exists())
            self.assertTrue((run_dir / "schedule_report.json").exists())
            self.assertTrue((run_dir / "routing_telemetry.json").exists())
            self.assertTrue((run_dir / "trace_report.json").exists())
            self.assertTrue((run_dir / "debug_bundle_manifest.json").exists())
            self.assertTrue((run_dir / "repo_validation_report.json").exists())
            self.assertTrue((run_dir / "delivery_bundle.zip").exists())
            self.assertTrue((run_dir / "zip_validation.json").exists())
            self.assertTrue((run_dir / "artifact_integrity_report.json").exists())
            self.assertTrue((run_dir / "checksums.json").exists())
            self.assertTrue((run_dir / "delivery_receipt.json").exists())
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

    def test_pipeline_runtime_snapshot_reaches_final_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Product\nBuild the kernel spine.")
            out = root / "runs"
            result = Orchestrator(out).run(
                HostInvocation(
                    prompt="Build a serious implementation report",
                    attachments=[InputAttachment(uri=str(source))],
                    cwd=str(root),
                )
            )

            snapshot = Orchestrator(out).runtime.resumable_snapshot(result.run_id)

        self.assertEqual(snapshot["latest_state"], "delivered")
        self.assertTrue(snapshot["tasks"])

    def test_deterministic_registry_declares_only_real_stage_capabilities(self) -> None:
        capabilities = CapabilityRegistry.from_environment().providers[0].capabilities

        self.assertNotIn("strategic_reasoning", capabilities)
        self.assertNotIn("final_synthesis", capabilities)
        self.assertNotIn("code_reasoning", capabilities)
        self.assertEqual(capabilities["context_aggregation"], 1.0)
        self.assertEqual(capabilities["quality_evaluation"], 1.0)


if __name__ == "__main__":
    unittest.main()
