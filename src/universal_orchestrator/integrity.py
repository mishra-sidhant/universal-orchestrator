from __future__ import annotations

from collections import Counter

from universal_orchestrator.models import (
    Artifact,
    ArtifactIntegrityEntry,
    ArtifactIntegrityReport,
)
from universal_orchestrator.utils import sha256_file


class ArtifactIntegrityAuditor:
    def audit(
        self,
        run_id: str,
        artifacts: list[Artifact],
        expected_names: list[str] | None = None,
    ) -> ArtifactIntegrityReport:
        entries = [self._entry(artifact) for artifact in artifacts]
        names = [artifact.name for artifact in artifacts]
        duplicate_names = sorted(name for name, count in Counter(names).items() if count > 1)
        expected = expected_names or []
        missing_expected = sorted(set(expected).difference(names))
        passed = (
            all(entry.exists and entry.hash_matches and not entry.errors for entry in entries)
            and not duplicate_names
            and not missing_expected
        )
        return ArtifactIntegrityReport(
            run_id=run_id,
            passed=passed,
            artifact_count=len(artifacts),
            duplicate_names=duplicate_names,
            missing_expected=missing_expected,
            entries=entries,
        )

    def _entry(self, artifact: Artifact) -> ArtifactIntegrityEntry:
        path = artifact.as_path
        errors: list[str] = []
        if not path.exists():
            return ArtifactIntegrityEntry(
                name=artifact.name,
                path=artifact.path,
                artifact_type=artifact.type,
                exists=False,
                content_hash=artifact.content_hash,
                hash_matches=False,
                errors=["Artifact path does not exist."],
            )
        actual_hash = sha256_file(path)
        if artifact.content_hash and actual_hash != artifact.content_hash:
            errors.append("Artifact content hash does not match recorded hash.")
        actual_size = path.stat().st_size
        if artifact.size_bytes is not None and actual_size != artifact.size_bytes:
            errors.append("Artifact size does not match recorded size.")
        return ArtifactIntegrityEntry(
            name=artifact.name,
            path=artifact.path,
            artifact_type=artifact.type,
            exists=True,
            size_bytes=actual_size,
            content_hash=actual_hash,
            hash_matches=actual_hash == artifact.content_hash,
            errors=errors,
        )
