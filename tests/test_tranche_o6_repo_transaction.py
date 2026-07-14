from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from universal_orchestrator.repo_transaction import RepositoryEdit, TransactionalRepoEditor


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class TrancheO6RepoTransactionTests(unittest.TestCase):
    def test_without_write_approval_no_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "src.py"
            path.write_text("before\n")

            report = TransactionalRepoEditor().apply(
                root,
                [RepositoryEdit(path="src.py", content="after\n")],
                run_id="R",
                allow_repo_writes=False,
            )
            unchanged = path.read_text()

        self.assertFalse(report.committed)
        self.assertIn("approval", report.errors[0].lower())
        self.assertEqual(unchanged, "before\n")

    def test_successful_apply_requires_expected_hash_and_records_after_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "src.py"
            path.write_text("before\n")

            report = TransactionalRepoEditor().apply(
                root,
                [
                    RepositoryEdit(
                        path="src.py",
                        content="after\n",
                        expected_sha256=digest(path),
                    ),
                    RepositoryEdit(path="new.py", content="new file\n"),
                ],
                run_id="R",
                allow_repo_writes=True,
            )

            self.assertTrue(report.committed)
            self.assertEqual(path.read_text(), "after\n")
            self.assertTrue((root / "new.py").exists())
            self.assertEqual(report.files[0].after_sha256, digest(path))

    def test_hash_mismatch_aborts_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.py"
            second = root / "second.py"
            first.write_text("first\n")
            second.write_text("second\n")

            report = TransactionalRepoEditor().apply(
                root,
                [
                    RepositoryEdit(path="first.py", content="changed\n"),
                    RepositoryEdit(
                        path="second.py",
                        content="changed second\n",
                        expected_sha256="sha256:not-current",
                    ),
                ],
                run_id="R",
                allow_repo_writes=True,
            )
            first_text = first.read_text()
            second_text = second.read_text()

        self.assertFalse(report.committed)
        self.assertIn("hash", " ".join(report.errors).lower())
        self.assertEqual(first_text, "first\n")
        self.assertEqual(second_text, "second\n")

    def test_secret_in_new_content_aborts_without_persisting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "config.py"
            report = TransactionalRepoEditor().apply(
                root,
                [RepositoryEdit(path="config.py", content="OPENAI_API_KEY=sk-secret-value\n")],
                run_id="R",
                allow_repo_writes=True,
            )

        self.assertFalse(report.committed)
        self.assertTrue(any("secret" in error.lower() for error in report.errors))
        self.assertFalse(path.exists())

    def test_mid_commit_failure_rolls_back_already_replaced_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.py"
            second = root / "second.py"
            first.write_text("first\n")
            second.write_text("second\n")
            first.chmod(0o755)
            real_replace = __import__("os").replace
            calls = 0

            def flaky_replace(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("forced replace failure")
                return real_replace(source, destination)

            with patch("universal_orchestrator.repo_transaction.os.replace", side_effect=flaky_replace):
                report = TransactionalRepoEditor().apply(
                    root,
                    [
                        RepositoryEdit(
                            path="first.py",
                            content="changed first\n",
                            expected_sha256=digest(first),
                        ),
                        RepositoryEdit(
                            path="second.py",
                            content="changed second\n",
                            expected_sha256=digest(second),
                        ),
                    ],
                    run_id="R",
                    allow_repo_writes=True,
                )
                first_text = first.read_text()
                second_text = second.read_text()
                first_mode = first.stat().st_mode & 0o777

        self.assertFalse(report.committed)
        self.assertTrue(report.rolled_back)
        self.assertEqual(first_text, "first\n")
        self.assertEqual(second_text, "second\n")
        self.assertEqual(first_mode, 0o755)

    def test_rollback_failure_is_reported_without_escaping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.py"
            second = root / "second.py"
            first.write_text("first\n")
            second.write_text("second\n")
            real_replace = __import__("os").replace
            calls = 0

            def flaky_replace(source, destination):
                nonlocal calls
                calls += 1
                if calls in {2, 3}:
                    raise OSError("forced replace failure")
                return real_replace(source, destination)

            with patch("universal_orchestrator.repo_transaction.os.replace", side_effect=flaky_replace):
                report = TransactionalRepoEditor().apply(
                    root,
                    [
                        RepositoryEdit(
                            path="first.py",
                            content="changed first\n",
                            expected_sha256=digest(first),
                        ),
                        RepositoryEdit(
                            path="second.py",
                            content="changed second\n",
                            expected_sha256=digest(second),
                        ),
                    ],
                    run_id="R",
                    allow_repo_writes=True,
                )

        self.assertFalse(report.committed)
        self.assertFalse(report.rolled_back)
        self.assertTrue(report.rollback_errors)
        self.assertTrue(any("rollback failed" in error.lower() for error in report.errors))

    def test_path_escape_and_protected_path_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            escape = TransactionalRepoEditor().apply(
                root,
                [RepositoryEdit(path="../outside.py", content="x")],
                run_id="R",
                allow_repo_writes=True,
            )
            protected = TransactionalRepoEditor().apply(
                root,
                [RepositoryEdit(path=".git/config", content="x")],
                run_id="R",
                allow_repo_writes=True,
            )

        self.assertFalse(escape.committed)
        self.assertFalse(protected.committed)
        self.assertTrue(any("path" in error.lower() for error in escape.errors))
        self.assertTrue(any("protected" in error.lower() for error in protected.errors))


if __name__ == "__main__":
    unittest.main()
