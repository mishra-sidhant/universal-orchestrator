from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from universal_orchestrator.models import StrictModel
from universal_orchestrator.security import scan_text
from universal_orchestrator.utils import sha256_bytes
from pydantic import Field


PROTECTED_DIRS = {".git", ".uo", ".venv", "venv", "node_modules"}
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:api[_-]?key|secret|token)\s*[:=]\s*[\"']?[^\s\"']{8,}"
)


class RepositoryEdit(StrictModel):
    path: str
    content: str
    expected_sha256: str | None = None
    reason: str = "Operator-approved repository edit."


class RepositoryEditFile(StrictModel):
    path: str
    existed_before: bool
    before_sha256: str | None = None
    after_sha256: str | None = None


class RepositoryEditReport(StrictModel):
    schema_version: str = "1.0"
    run_id: str
    root: str
    attempted: bool = False
    committed: bool = False
    rolled_back: bool = False
    files: list[RepositoryEditFile] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TransactionalRepoEditor:
    """Apply a bounded set of text edits with preflight checks and rollback."""

    def apply(
        self,
        root: Path | str,
        edits: list[RepositoryEdit],
        *,
        run_id: str,
        allow_repo_writes: bool,
    ) -> RepositoryEditReport:
        repo_root = Path(root).expanduser().resolve()
        report = RepositoryEditReport(
            run_id=run_id,
            root=str(repo_root),
            attempted=bool(edits),
        )
        if not allow_repo_writes:
            report.errors.append(
                "Repository write approval is required; no files were changed."
            )
            return report
        if not repo_root.is_dir():
            report.errors.append(f"Repository root is not a directory: {repo_root}")
            return report
        if not edits:
            report.committed = True
            return report

        prepared: list[tuple[RepositoryEdit, Path, bytes | None, int | None]] = []
        seen: set[Path] = set()
        for edit in edits:
            path, error = self._confined_path(repo_root, edit.path)
            if path is None:
                report.errors.append(error or f"Repository edit path is invalid: {edit.path}")
                continue
            if path in seen:
                report.errors.append(f"Duplicate repository edit path: {edit.path}")
                continue
            seen.add(path)
            if path.exists() and not path.is_file():
                report.errors.append(f"Repository edit target is not a file: {edit.path}")
                continue
            current = path.read_bytes() if path.exists() else None
            before_hash = sha256_bytes(current) if current is not None else None
            if edit.expected_sha256 is not None and edit.expected_sha256 != before_hash:
                report.errors.append(
                    f"Repository edit hash mismatch for {edit.path}: "
                    f"expected {edit.expected_sha256}, found {before_hash}."
                )
                continue
            findings = scan_text(edit.content, location=edit.path)
            if findings or SECRET_ASSIGNMENT.search(edit.content):
                report.errors.append(
                    f"Repository edit content contains secret material and was rejected: {edit.path}"
                )
                continue
            report.files.append(
                RepositoryEditFile(
                    path=edit.path,
                    existed_before=current is not None,
                    before_sha256=before_hash,
                )
            )
            prepared.append((edit, path, current, path.stat().st_mode if path.exists() else None))

        if report.errors:
            return report

        staged: list[tuple[Path, Path]] = []
        backups: dict[Path, tuple[bytes | None, int | None]] = {
            path: (current, mode) for _, path, current, mode in prepared
        }
        replaced: list[Path] = []
        try:
            for edit, path, _, _ in prepared:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=f".{path.name}.uo-tx-",
                    dir=path.parent,
                    delete=False,
                ) as handle:
                    handle.write(edit.content.encode("utf-8"))
                    handle.flush()
                    os.fsync(handle.fileno())
                    staged.append((Path(handle.name), path))
            for temporary, destination in staged:
                os.replace(temporary, destination)
                replaced.append(destination)
            for index, (_, path, _, _) in enumerate(prepared):
                after_hash = sha256_bytes(path.read_bytes())
                report.files[index] = report.files[index].model_copy(
                    update={"after_sha256": after_hash}
                )
                if after_hash != sha256_bytes(prepared[index][0].content.encode("utf-8")):
                    raise OSError(f"Post-commit hash verification failed for {path}")
            report.committed = True
            return report
        except Exception as exc:
            report.errors.append(f"Repository transaction failed: {type(exc).__name__}: {exc}")
            self._rollback(replaced, backups)
            report.rolled_back = bool(replaced)
            return report
        finally:
            for temporary, _ in staged:
                temporary.unlink(missing_ok=True)

    def _confined_path(self, root: Path, raw_path: str) -> tuple[Path | None, str | None]:
        candidate = Path(raw_path).expanduser()
        path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            return None, f"Repository edit path escapes repository root: {raw_path}"
        if any(part in PROTECTED_DIRS for part in path.relative_to(root).parts):
            return None, f"Repository edit path is protected: {raw_path}"
        return path, None

    def _rollback(
        self,
        replaced: list[Path],
        backups: dict[Path, tuple[bytes | None, int | None]],
    ) -> None:
        for path in reversed(replaced):
            original, mode = backups[path]
            if original is None:
                path.unlink(missing_ok=True)
                continue
            with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as handle:
                handle.write(original)
                handle.flush()
                os.fsync(handle.fileno())
                rollback_path = Path(handle.name)
            os.replace(rollback_path, path)
            if mode is not None:
                path.chmod(mode)
