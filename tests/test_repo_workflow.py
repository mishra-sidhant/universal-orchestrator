from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from universal_orchestrator.repo_transaction import RepositoryEdit, TransactionalRepoEditor
from universal_orchestrator.repo_workflow import RepositoryWorkflow
from universal_orchestrator.utils import sha256_bytes


class RepositoryWorkflowTests(unittest.TestCase):
    def test_prepare_and_apply_requires_matching_digest_and_preserves_hash_fence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "source.py"
            target.write_text("before\n")
            workflow = RepositoryWorkflow()
            changeset = workflow.prepare(
                root,
                run_id="repo-test",
                edits=[
                    RepositoryEdit(
                        path="source.py",
                        content="after\n",
                        expected_sha256=sha256_bytes(b"before\n"),
                    )
                ],
            )

            rejected = workflow.apply(
                changeset,
                approval_digest="wrong",
                allow_repo_writes=True,
            )
            self.assertFalse(rejected.committed)
            self.assertEqual(target.read_text(), "before\n")

            committed = workflow.apply(
                changeset,
                approval_digest=changeset.approval_digest,
                allow_repo_writes=True,
            )
            self.assertTrue(committed.committed)
            self.assertEqual(target.read_text(), "after\n")

    def test_changed_source_is_rejected_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "source.py"
            target.write_text("before\n")
            workflow = RepositoryWorkflow()
            changeset = workflow.prepare(
                root,
                run_id="repo-stale",
                edits=[
                    RepositoryEdit(
                        path="source.py",
                        content="after\n",
                        expected_sha256=sha256_bytes(b"before\n"),
                    )
                ],
            )
            target.write_text("operator-change\n")

            report = workflow.apply(
                changeset,
                approval_digest=changeset.approval_digest,
                allow_repo_writes=True,
            )
            self.assertFalse(report.committed)
            self.assertIn("hash mismatch", report.errors[0])
            self.assertEqual(target.read_text(), "operator-change\n")

    def test_transaction_can_delete_with_expected_hash_and_rollback_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "remove-me.txt"
            target.write_text("remove\n")
            report = TransactionalRepoEditor().apply(
                root,
                [
                    RepositoryEdit(
                        path=target.name,
                        delete=True,
                        expected_sha256=sha256_bytes(b"remove\n"),
                    )
                ],
                run_id="repo-delete",
                allow_repo_writes=True,
            )
            self.assertTrue(report.committed)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
