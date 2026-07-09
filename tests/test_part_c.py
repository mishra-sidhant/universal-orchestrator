import tempfile
import unittest
from json import loads
from pathlib import Path

from universal_orchestrator.approvals import ApprovalGateEngine
from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.daemon import daemon_artifacts, daemon_cancel, daemon_status
from universal_orchestrator.evals import EvaluationRunner
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.integrity import ArtifactIntegrityAuditor
from universal_orchestrator.models import Artifact, ArtifactType, HostInvocation, InputAttachment, PrivacyMode, UserOptions
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.repo_validation import RepoValidationRunner


class PartCGapTests(unittest.TestCase):
    def test_approval_report_blocks_unapproved_network_fetch(self) -> None:
        invocation = HostInvocation(
            prompt="Summarize this URL",
            attachments=[InputAttachment(uri="https://example.com/report")],
            user_options=UserOptions(allow_internet=False),
        )
        manifest = InputIngestor().ingest(invocation, "run_test")
        contract = ProductContractCompiler().compile(invocation, manifest)

        report = ApprovalGateEngine().evaluate(invocation, manifest, contract)

        internet_gate = next(gate for gate in report.gates if gate.name == "internet_access")
        self.assertTrue(internet_gate.required)
        self.assertFalse(internet_gate.granted)
        self.assertTrue(report.blocked)

    def test_approval_report_blocks_cloud_for_local_only_privacy(self) -> None:
        invocation = HostInvocation(
            prompt="Analyze locally",
            user_options=UserOptions(privacy_mode=PrivacyMode.LOCAL_ONLY),
        )
        manifest = InputIngestor().ingest(invocation, "run_test")
        contract = ProductContractCompiler().compile(invocation, manifest)

        report = ApprovalGateEngine().evaluate(invocation, manifest, contract)

        cloud_gate = next(gate for gate in report.gates if gate.name == "cloud_provider_execution")
        self.assertTrue(cloud_gate.required)
        self.assertFalse(cloud_gate.granted)
        self.assertTrue(report.blocked)

    def test_approval_report_does_not_block_default_local_run(self) -> None:
        invocation = HostInvocation(prompt="Analyze local notes")
        manifest = InputIngestor().ingest(invocation, "run_test")
        contract = ProductContractCompiler().compile(invocation, manifest)

        report = ApprovalGateEngine().evaluate(invocation, manifest, contract)

        self.assertFalse(report.blocked)

    def test_pipeline_writes_approval_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Product\nBuild the kernel spine.")
            result = Orchestrator(root / "runs").run(
                HostInvocation(
                    prompt="Build a serious implementation report",
                    attachments=[InputAttachment(uri=str(source))],
                    cwd=str(root),
                )
            )

            self.assertTrue((Path(result.artifact_dir) / "approval_report.json").exists())

    def test_repo_validation_skips_without_shell_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._sample_python_repo(Path(tmp))
            invocation = HostInvocation(
                prompt="Validate repo",
                attachments=[InputAttachment(uri=str(repo))],
                cwd=str(repo),
                user_options=UserOptions(allow_shell=False),
            )
            manifest = InputIngestor().ingest(invocation, "run_test")

            report = RepoValidationRunner().run(invocation, manifest)

        self.assertFalse(report.executed)
        self.assertEqual(report.command_results[0].status, "skipped")

    def test_repo_validation_executes_allowlisted_unittest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._sample_python_repo(Path(tmp))
            invocation = HostInvocation(
                prompt="Validate repo",
                attachments=[InputAttachment(uri=str(repo))],
                cwd=str(repo),
                user_options=UserOptions(allow_shell=True),
            )
            manifest = InputIngestor().ingest(invocation, "run_test")

            report = RepoValidationRunner().run(invocation, manifest)

        self.assertTrue(report.executed)
        self.assertTrue(report.passed)
        self.assertEqual(report.command_results[0].status, "passed")

    def test_pipeline_writes_repo_validation_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._sample_python_repo(Path(tmp))
            result = Orchestrator(repo / "runs").run(
                HostInvocation(
                    prompt="Validate this repo implementation",
                    attachments=[InputAttachment(uri=str(repo))],
                    cwd=str(repo),
                    user_options=UserOptions(allow_shell=False),
                )
            )

            report = loads((Path(result.artifact_dir) / "repo_validation_report.json").read_text())

        self.assertFalse(report["executed"])
        self.assertEqual(report["command_results"][0]["status"], "skipped")

    def test_pipeline_writes_patch_plan_for_repo_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._sample_python_repo(Path(tmp))
            result = Orchestrator(repo / "runs").run(
                HostInvocation(
                    prompt="Implement improvements for this repo",
                    attachments=[InputAttachment(uri=str(repo))],
                    cwd=str(repo),
                )
            )

            run_dir = Path(result.artifact_dir)
            patch_text = (run_dir / "implementation_patch.diff").read_text()
            patch_validation = loads((run_dir / "patch_validation.json").read_text())

        self.assertTrue(patch_text.startswith("diff --git "))
        self.assertEqual(patch_validation["errors"], [])

    def test_pipeline_writes_delivery_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Product\nBuild the kernel spine.")
            result = Orchestrator(root / "runs").run(
                HostInvocation(
                    prompt="Build a serious implementation report",
                    attachments=[InputAttachment(uri=str(source))],
                    cwd=str(root),
                )
            )

            run_dir = Path(result.artifact_dir)
            zip_validation = loads((run_dir / "zip_validation.json").read_text())
            self.assertTrue((run_dir / "delivery_bundle.zip").exists())

        self.assertEqual(zip_validation["errors"], [])

    def test_artifact_integrity_detects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.json"
            path.write_text("{}")
            artifact = Artifact(
                type=ArtifactType.JSON,
                name=path.name,
                path=str(path),
                content_hash="sha256:not-real",
                size_bytes=path.stat().st_size,
            )

            report = ArtifactIntegrityAuditor().audit("run_test", [artifact], [path.name])

        self.assertFalse(report.passed)
        self.assertFalse(report.entries[0].hash_matches)

    def test_pipeline_writes_passing_artifact_integrity_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Product\nBuild the kernel spine.")
            result = Orchestrator(root / "runs").run(
                HostInvocation(
                    prompt="Build a serious implementation report",
                    attachments=[InputAttachment(uri=str(source))],
                    cwd=str(root),
                )
            )

            report = loads((Path(result.artifact_dir) / "artifact_integrity_report.json").read_text())

        self.assertTrue(report["passed"])
        self.assertEqual(report["missing_expected"], [])

    def test_daemon_helpers_expose_artifacts_status_and_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Product\nBuild the kernel spine.")
            runs_root = root / "runs"
            result = Orchestrator(runs_root).run(
                HostInvocation(
                    prompt="Build a serious implementation report",
                    attachments=[InputAttachment(uri=str(source))],
                    cwd=str(root),
                )
            )

            artifacts = daemon_artifacts(runs_root)
            status = daemon_status(result.run_id, runs_root)
            cancel = daemon_cancel(result.run_id, root=runs_root)

        self.assertIn(result.artifact_dir, artifacts["runs"])
        self.assertEqual(status["run_id"], result.run_id)
        self.assertIn("runtime_snapshot", status)
        self.assertFalse(cancel["accepted"])

    def test_evaluation_runner_writes_eval_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = EvaluationRunner().run(root=Path(tmp) / "evals", case_ids=["unsafe_archive"])

            report_path = Path(report.report_path or "")
            payload = loads(report_path.read_text())

        self.assertTrue(report.passed)
        self.assertEqual(report_path.name, "eval_report.json")
        self.assertEqual(payload["cases"][0]["case_id"], "unsafe_archive")

    def _sample_python_repo(self, root: Path) -> Path:
        repo = root / "repo"
        tests = repo / "tests"
        tests.mkdir(parents=True)
        (repo / ".git").mkdir()
        (repo / "README.md").write_text("# sample")
        (tests / "test_ok.py").write_text(
            "import unittest\n\n"
            "class OkTests(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n"
        )
        return repo


if __name__ == "__main__":
    unittest.main()
