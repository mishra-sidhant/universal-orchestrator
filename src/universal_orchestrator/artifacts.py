from __future__ import annotations

from pathlib import Path
from typing import Any

from universal_orchestrator.models import (
    Artifact,
    ArtifactType,
    RunManifest,
)
from universal_orchestrator.utils import ensure_dir, sha256_file, write_json


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = ensure_dir(root)

    def run_dir(self, run_id: str) -> Path:
        return ensure_dir(self.root / run_id)

    def write_json_artifact(self, run_id: str, name: str, payload: Any) -> Artifact:
        path = self.run_dir(run_id) / name
        write_json(path, payload)
        return self._artifact(path, ArtifactType.JSON)

    def write_text_artifact(self, run_id: str, name: str, content: str, artifact_type: ArtifactType) -> Artifact:
        path = self.run_dir(run_id) / name
        ensure_dir(path.parent)
        path.write_text(content)
        return self._artifact(path, artifact_type)

    def write_existing_artifact(self, path: Path, artifact_type: ArtifactType) -> Artifact:
        return self._artifact(path, artifact_type)

    def write_run_manifest(self, run_manifest: RunManifest) -> Artifact:
        path = self.run_dir(run_manifest.run_id) / "run_manifest.json"
        write_json(path, run_manifest.model_dump(mode="json"))
        return self._artifact(path, ArtifactType.MANIFEST)

    def _artifact(self, path: Path, artifact_type: ArtifactType) -> Artifact:
        return Artifact(
            type=artifact_type,
            name=path.name,
            path=str(path),
            content_hash=sha256_file(path),
            size_bytes=path.stat().st_size,
        )
