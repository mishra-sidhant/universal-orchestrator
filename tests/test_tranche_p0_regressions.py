from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from universal_orchestrator.fidelity import ContextArtifactFidelityAuditor
from universal_orchestrator.models import (
    ArtifactIntegrityReport,
    ContextChunk,
    ContextPack,
    FidelityFinding,
    FidelityReport,
    HostInvocation,
    RunState,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.repo_transaction import RepositoryEdit, TransactionalRepoEditor


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


class TrancheP0RegressionTests(unittest.TestCase):
    def test_context_text_tamper_fails_even_when_declared_hash_is_retained(self) -> None:
        canonical = ContextChunk(
            id="chunk-1",
            input_id="input-1",
            ordinal=0,
            text="Canonical content.",
            token_estimate=3,
            content_hash=digest_bytes(b"Canonical content."),
        )
        tampered = canonical.model_copy(update={"text": "Tampered content."})

        report = ContextArtifactFidelityAuditor().audit(
            "R",
            [canonical],
            {"T-SYNTHESIS": ContextPack(task_id="T-SYNTHESIS", task="Answer", chunks=[tampered])},
            [],
            {},
            [],
        )

        self.assertFalse(report.passed)

    def test_canonical_chunk_with_false_declared_hash_fails(self) -> None:
        canonical = ContextChunk(
            id="chunk-1",
            input_id="input-1",
            ordinal=0,
            text="Canonical content.",
            token_estimate=3,
            content_hash="sha256:not-the-content",
        )

        report = ContextArtifactFidelityAuditor().audit(
            "R",
            [canonical],
            {"T-SYNTHESIS": ContextPack(task_id="T-SYNTHESIS", task="Answer", chunks=[canonical])},
            [],
            {},
            [],
        )

        self.assertFalse(report.passed)

    def test_fidelity_failure_blocks_delivery_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = Orchestrator(Path(tmp) / "runs")
            orchestrator.fidelity.audit = lambda *args, **kwargs: FidelityReport(
                run_id="forced",
                passed=False,
                findings=[
                    FidelityFinding(
                        kind="forced",
                        passed=False,
                        severity="high",
                        message="forced fidelity failure",
                    )
                ],
            )
            result = orchestrator.run(HostInvocation(prompt="Produce a report"))
            run_dir = Path(result.artifact_dir)

        self.assertEqual(result.state, RunState.NEEDS_ATTENTION)
        self.assertFalse(result.quality.passed)
        self.assertFalse((run_dir / "delivery_receipt.json").exists())
        self.assertEqual(result.manifest.state, RunState.NEEDS_ATTENTION)

    def test_integrity_failure_blocks_delivery_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = Orchestrator(Path(tmp) / "runs")
            orchestrator.integrity.audit = lambda *args, **kwargs: ArtifactIntegrityReport(
                run_id="forced",
                passed=False,
                missing_expected=["forced-artifact"],
            )
            result = orchestrator.run(HostInvocation(prompt="Produce a report"))
            run_dir = Path(result.artifact_dir)

        self.assertEqual(result.state, RunState.NEEDS_ATTENTION)
        self.assertFalse(result.quality.passed)
        self.assertFalse((run_dir / "delivery_receipt.json").exists())
        self.assertEqual(result.manifest.state, RunState.NEEDS_ATTENTION)

    def test_existing_edit_without_expected_hash_is_rejected_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "source.py"
            target.write_text("before\n")

            report = TransactionalRepoEditor().apply(
                root,
                [RepositoryEdit(path=target.name, content="after\n")],
                run_id="R",
                allow_repo_writes=True,
            )

            self.assertFalse(report.committed)
            self.assertIn("expected", " ".join(report.errors).lower())
            self.assertEqual(target.read_text(), "before\n")

    def test_existing_edit_preserves_executable_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "run.sh"
            target.write_text("#!/bin/sh\nexit 0\n")
            target.chmod(0o755)

            report = TransactionalRepoEditor().apply(
                root,
                [
                    RepositoryEdit(
                        path=target.name,
                        content="#!/bin/sh\nexit 1\n",
                        expected_sha256=digest_bytes(target.read_bytes()),
                    )
                ],
                run_id="R",
                allow_repo_writes=True,
            )

            self.assertTrue(report.committed)
            self.assertEqual(target.stat().st_mode & 0o777, 0o755)

    def test_new_edit_uses_safe_default_mode_and_accepts_explicit_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            default_target = root / "new.py"
            explicit_target = root / "private.py"

            default_report = TransactionalRepoEditor().apply(
                root,
                [RepositoryEdit(path=default_target.name, content="print(1)\n")],
                run_id="R-default",
                allow_repo_writes=True,
            )
            explicit_report = TransactionalRepoEditor().apply(
                root,
                [
                    RepositoryEdit(
                        path=explicit_target.name,
                        content="print(2)\n",
                        mode=0o700,
                    )
                ],
                run_id="R-explicit",
                allow_repo_writes=True,
            )

            self.assertTrue(default_report.committed)
            self.assertTrue(explicit_report.committed)
            self.assertEqual(default_target.stat().st_mode & 0o777, 0o644)
            self.assertEqual(explicit_target.stat().st_mode & 0o777, 0o700)

    def test_destination_change_after_staging_aborts_before_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "source.py"
            target.write_text("before\n")
            editor = TransactionalRepoEditor()
            original_verify = editor._verify_live_targets

            def mutate_then_verify(prepared: object) -> None:
                target.write_text("external change\n")
                original_verify(prepared)  # type: ignore[arg-type]

            with patch.object(editor, "_verify_live_targets", side_effect=mutate_then_verify):
                report = editor.apply(
                    root,
                    [
                        RepositoryEdit(
                            path=target.name,
                            content="after\n",
                            expected_sha256=digest_bytes(b"before\n"),
                        )
                    ],
                    run_id="R",
                    allow_repo_writes=True,
                )

            self.assertFalse(report.committed)
            self.assertIn("changed after preflight", " ".join(report.errors))
            self.assertEqual(target.read_text(), "external change\n")


if __name__ == "__main__":
    unittest.main()
