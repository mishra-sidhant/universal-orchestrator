"""Approval-bound repository change-set and isolated worktree lifecycle."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from universal_orchestrator.repo_transaction import (
    RepositoryEdit,
    RepositoryEditReport,
    TransactionalRepoEditor,
)
from universal_orchestrator.utils import sha256_bytes


class RepositoryChangeSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    run_id: str
    root: str
    base_revision: str | None = None
    source_fingerprint: str
    dirty: bool = False
    edits: list[RepositoryEdit] = Field(default_factory=list)
    approval_digest: str
    warnings: list[str] = Field(default_factory=list)


class WorktreeReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    source_root: str
    worktree: str
    base_revision: str
    created: bool


class RepositoryWorkflow:
    def __init__(self, editor: TransactionalRepoEditor | None = None) -> None:
        self.editor = editor or TransactionalRepoEditor()

    def snapshot(self, root: Path | str) -> dict[str, Any]:
        repository = Path(root).expanduser().resolve()
        revision = self._git(repository, "rev-parse", "HEAD", check=False)
        status = self._git(repository, "status", "--porcelain", "--untracked-files=all", check=False)
        dirty = bool(status)
        payload = {"root": str(repository), "revision": revision, "dirty": dirty, "status": status}
        payload["fingerprint"] = sha256_bytes(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        )
        return payload

    def prepare(
        self,
        root: Path | str,
        *,
        run_id: str,
        edits: list[RepositoryEdit],
        allow_dirty_snapshot: bool = False,
    ) -> RepositoryChangeSet:
        snapshot = self.snapshot(root)
        warnings: list[str] = []
        if snapshot["revision"] is None:
            warnings.append("Repository is not a Git worktree; branch publication is unavailable.")
        if snapshot["dirty"] and not allow_dirty_snapshot:
            warnings.append("Source worktree is dirty; publication requires a clean worktree.")
        payload = {
            "run_id": run_id,
            "root": str(Path(root).expanduser().resolve()),
            "base_revision": snapshot["revision"],
            "source_fingerprint": snapshot["fingerprint"],
            "dirty": snapshot["dirty"],
            "edits": [edit.model_dump(mode="json") for edit in edits],
        }
        digest = sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))
        return RepositoryChangeSet(
            **payload,
            approval_digest=digest,
            warnings=warnings,
        )

    def apply(
        self,
        changeset: RepositoryChangeSet,
        *,
        approval_digest: str,
        allow_repo_writes: bool,
        root_override: Path | str | None = None,
    ) -> RepositoryEditReport:
        if approval_digest != changeset.approval_digest:
            return RepositoryEditReport(
                run_id=changeset.run_id,
                root=changeset.root,
                attempted=bool(changeset.edits),
                errors=["Repository approval digest does not match the prepared change set."],
            )
        root = Path(root_override or changeset.root).expanduser().resolve()
        current = self.snapshot(root)
        if current["fingerprint"] != changeset.source_fingerprint:
            return RepositoryEditReport(
                run_id=changeset.run_id,
                root=str(root),
                attempted=bool(changeset.edits),
                errors=["Repository changed after preparation; prepare a new change set."],
            )
        return self.editor.apply(
            root,
            changeset.edits,
            run_id=changeset.run_id,
            allow_repo_writes=allow_repo_writes,
        )

    def create_worktree(
        self,
        root: Path | str,
        *,
        run_id: str,
        destination: Path | str,
        allow_dirty_snapshot: bool = False,
    ) -> WorktreeReceipt:
        repository = Path(root).expanduser().resolve()
        snapshot = self.snapshot(repository)
        revision = snapshot["revision"]
        if revision is None:
            raise RuntimeError("An isolated implementation worktree requires a Git repository.")
        if snapshot["dirty"] and not allow_dirty_snapshot:
            raise RuntimeError("Source worktree is dirty; isolate from a clean revision or explicitly allow a snapshot.")
        worktree = Path(destination).expanduser().resolve()
        worktree.parent.mkdir(parents=True, exist_ok=True)
        if worktree.exists():
            raise RuntimeError(f"Worktree destination already exists: {worktree}")
        self._git(repository, "worktree", "add", "--detach", str(worktree), revision)
        return WorktreeReceipt(
            run_id=run_id,
            source_root=str(repository),
            worktree=str(worktree),
            base_revision=revision,
            created=True,
        )

    def publish(
        self,
        worktree: Path | str,
        *,
        branch: str,
        commit_message: str | None = None,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", branch) or branch.startswith("/"):
            raise ValueError("Branch name contains unsupported characters.")
        root = Path(worktree).expanduser().resolve()
        self._git(root, "switch", "-c", branch)
        payload: dict[str, Any] = {"worktree": str(root), "branch": branch, "committed": False}
        if commit_message is not None:
            if not commit_message.strip():
                raise ValueError("Commit message must not be empty.")
            self._git(root, "add", "--all")
            self._git(root, "commit", "-m", commit_message)
            payload["committed"] = True
            payload["commit"] = self._git(root, "rev-parse", "HEAD")
        return payload

    def write_changeset(self, changeset: RepositoryChangeSet, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(changeset.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
        os.replace(temporary, target)
        return target

    def read_changeset(self, path: Path | str) -> RepositoryChangeSet:
        return RepositoryChangeSet.model_validate(json.loads(Path(path).read_text()))

    def _git(self, root: Path, *args: str, check: bool = True) -> str | None:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            env={key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ},
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            if check:
                raise RuntimeError((completed.stderr or completed.stdout).strip() or "Git command failed.")
            return None
        return completed.stdout.strip()
