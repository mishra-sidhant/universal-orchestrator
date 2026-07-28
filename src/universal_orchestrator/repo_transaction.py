from __future__ import annotations

import os
import re
import stat
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
    content: str = ""
    delete: bool = False
    expected_sha256: str | None = None
    mode: int | None = Field(default=None, ge=0, le=0o777)
    reason: str = "Operator-approved repository edit."


class RepositoryEditFile(StrictModel):
    path: str
    existed_before: bool
    before_sha256: str | None = None
    after_sha256: str | None = None
    before_mode: int | None = None
    after_mode: int | None = None


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
    rollback_errors: list[str] = Field(default_factory=list)


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

        prepared: list[tuple[RepositoryEdit, Path, bytes | None, int | None, int]] = []
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
            before_mode = stat.S_IMODE(path.stat().st_mode) if current is not None else None
            if edit.delete and current is None:
                report.errors.append(f"Repository delete target does not exist: {edit.path}")
                continue
            if current is not None and edit.expected_sha256 is None:
                report.errors.append(
                    f"Repository edit requires expected_sha256 for existing file: {edit.path}"
                )
                continue
            if current is None and edit.expected_sha256 is not None:
                report.errors.append(
                    f"Repository edit expected_sha256 must be absent for new file: {edit.path}"
                )
                continue
            if edit.expected_sha256 is not None and edit.expected_sha256 != before_hash:
                report.errors.append(
                    f"Repository edit hash mismatch for {edit.path}: "
                    f"expected {edit.expected_sha256}, found {before_hash}."
                )
                continue
            findings = [] if edit.delete else scan_text(edit.content, location=edit.path)
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
                    before_mode=before_mode,
                )
            )
            effective_mode = edit.mode if edit.mode is not None else (before_mode or 0o644)
            prepared.append((edit, path, current, before_mode, effective_mode))

        if report.errors:
            return report

        staged: list[tuple[Path, Path]] = []
        backups: dict[Path, tuple[bytes | None, int | None]] = {
            path: (current, before_mode) for _, path, current, before_mode, _ in prepared
        }
        replaced: list[Path] = []
        try:
            for edit, path, _, _, effective_mode in prepared:
                if edit.delete:
                    continue
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=f".{path.name}.uo-tx-",
                    dir=path.parent,
                    delete=False,
                ) as handle:
                    handle.write(edit.content.encode("utf-8"))
                    os.fchmod(handle.fileno(), effective_mode)
                    handle.flush()
                    os.fsync(handle.fileno())
                    staged.append((Path(handle.name), path))
            self._verify_live_targets(prepared)
            for edit, path, _, _, effective_mode in prepared:
                if edit.delete:
                    path.unlink()
                    replaced.append(path)
                    self._fsync_parent(path)
            for temporary, destination in staged:
                os.replace(temporary, destination)
                replaced.append(destination)
                self._fsync_parent(destination)
            for index, (edit, path, _, _, effective_mode) in enumerate(prepared):
                after_exists = path.exists()
                after_hash = sha256_bytes(path.read_bytes()) if after_exists else None
                after_mode = stat.S_IMODE(path.stat().st_mode) if after_exists else None
                report.files[index] = report.files[index].model_copy(
                    update={"after_sha256": after_hash, "after_mode": after_mode}
                )
                if edit.delete and after_exists:
                    raise OSError(f"Post-commit delete verification failed for {path}")
                if not edit.delete and after_hash != sha256_bytes(edit.content.encode("utf-8")):
                    raise OSError(f"Post-commit hash verification failed for {path}")
                if not edit.delete and after_mode != effective_mode:
                    raise OSError(f"Post-commit mode verification failed for {path}")
            report.committed = True
            return report
        except Exception as exc:
            report.errors.append(f"Repository transaction failed: {type(exc).__name__}: {exc}")
            report.rollback_errors.extend(self._rollback(replaced, backups))
            report.rolled_back = bool(replaced) and not report.rollback_errors
            if report.rollback_errors:
                report.errors.extend(
                    f"Rollback failed: {error}" for error in report.rollback_errors
                )
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
    ) -> list[str]:
        errors: list[str] = []
        for path in reversed(replaced):
            original, mode = backups[path]
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                    self._fsync_parent(path)
                    continue
                rollback_path: Path | None = None
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=path.parent, delete=False
                ) as handle:
                    handle.write(original)
                    os.fchmod(handle.fileno(), mode if mode is not None else 0o644)
                    handle.flush()
                    os.fsync(handle.fileno())
                    rollback_path = Path(handle.name)
                os.replace(rollback_path, path)
                if mode is not None:
                    path.chmod(mode)
                self._fsync_parent(path)
            except Exception as exc:
                errors.append(f"{path}: {type(exc).__name__}: {exc}")
            finally:
                if rollback_path is not None:
                    rollback_path.unlink(missing_ok=True)
        return errors

    def _verify_live_targets(
        self,
        prepared: list[tuple[RepositoryEdit, Path, bytes | None, int | None, int]],
    ) -> None:
        for _, path, current, before_mode, _ in prepared:
            live = path.read_bytes() if path.exists() else None
            live_mode = stat.S_IMODE(path.stat().st_mode) if live is not None else None
            if live != current or live_mode != before_mode:
                raise OSError(f"Repository edit target changed after preflight: {path}")

    def _fsync_parent(self, path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path.parent, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
