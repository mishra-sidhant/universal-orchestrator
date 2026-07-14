from __future__ import annotations

from pathlib import Path

from universal_orchestrator.models import (
    Artifact,
    ContextChunk,
    ContextPack,
    ExecutionResult,
    FidelityFinding,
    FidelityReport,
    task_succeeded,
)
from universal_orchestrator.utils import sha256_bytes, sha256_file


class ContextArtifactFidelityAuditor:
    def audit(
        self,
        run_id: str,
        chunks: list[ContextChunk],
        context_packs: dict[str, ContextPack],
        results: list[ExecutionResult],
        consumed_chunk_refs_by_task: dict[str, list[str]],
        artifacts: list[Artifact],
    ) -> FidelityReport:
        findings: list[FidelityFinding] = []
        canonical: dict[str, ContextChunk] = {}
        duplicate_ids: set[str] = set()
        for chunk in chunks:
            if chunk.id in canonical:
                duplicate_ids.add(chunk.id)
            canonical[chunk.id] = chunk
        for chunk_id in sorted(duplicate_ids):
            findings.append(
                FidelityFinding(
                    kind="canonical_chunk_identity",
                    passed=False,
                    severity="critical",
                    message=f"Canonical context contains duplicate chunk ID: {chunk_id}.",
                    metadata={"chunk_id": chunk_id},
                )
            )
        pack_count = len(context_packs)
        for task_id, pack in context_packs.items():
            for chunk in pack.chunks:
                source = canonical.get(chunk.id)
                passed = source is not None and self._chunk_identity_matches(source, chunk)
                findings.append(
                    FidelityFinding(
                        kind="context_pack_chunk",
                        passed=passed,
                        severity="high",
                        message=(
                            "Context-pack chunk matches the canonical ingested chunk."
                            if passed
                            else f"Context-pack chunk content hash, bytes, or identity do not match canonical input for {task_id}: {chunk.id}."
                        ),
                        metadata={
                            "task_id": task_id,
                            "chunk_id": chunk.id,
                            "canonical_declared_hash": source.content_hash if source else None,
                            "canonical_computed_hash": (
                                self._text_hash(source.text) if source else None
                            ),
                            "pack_declared_hash": chunk.content_hash,
                            "pack_computed_hash": self._text_hash(chunk.text),
                        },
                    )
                )

        manuscript_sections = 0
        valid_ids = set(canonical)
        for result in results:
            if not task_succeeded(result.status):
                continue
            worker = result.output.get("worker_output", {})
            if not isinstance(worker, dict):
                continue
            consumed = set(consumed_chunk_refs_by_task.get(result.task_id, []))
            refs = {str(ref) for ref in worker.get("evidence_refs", []) if ref}
            valid_refs = refs.issubset(valid_ids) and refs.issubset(consumed)
            findings.append(
                FidelityFinding(
                    kind="worker_context_consumption",
                    passed=valid_refs,
                    severity="high",
                    message=(
                        "Worker evidence refs are valid and consumed by the task."
                        if valid_refs
                        else f"Worker evidence refs exceed the task's consumed context: {result.task_id}."
                    ),
                    metadata={"task_id": result.task_id, "refs": sorted(refs)},
                )
            )
            sections = worker.get("manuscript", [])
            if isinstance(sections, list):
                manuscript_sections += len(sections)
                for section in sections:
                    if not isinstance(section, dict):
                        continue
                    section_refs = {str(ref) for ref in section.get("evidence_refs", []) if ref}
                    section_ok = section_refs.issubset(valid_ids) and section_refs.issubset(consumed)
                    findings.append(
                        FidelityFinding(
                            kind="manuscript_context_consumption",
                            passed=section_ok,
                            severity="high",
                            message=(
                                "Manuscript section refs are valid and consumed by the task."
                                if section_ok
                                else f"Manuscript section refs exceed the task's consumed context: {result.task_id}."
                            ),
                            metadata={"task_id": result.task_id, "refs": sorted(section_refs)},
                        )
                    )

        for artifact in artifacts:
            path = Path(artifact.path)
            passed = (
                path.exists()
                and artifact.content_hash is not None
                and sha256_file(path) == artifact.content_hash
                and (artifact.size_bytes is None or path.stat().st_size == artifact.size_bytes)
            )
            findings.append(
                FidelityFinding(
                    kind="artifact_fidelity",
                    passed=passed,
                    severity="high",
                    message=(
                        "Artifact bytes match the recorded content hash and size."
                        if passed
                        else f"Artifact bytes do not match the recorded identity: {artifact.name}."
                    ),
                    metadata={"artifact": artifact.name},
                )
            )
        return FidelityReport(
            run_id=run_id,
            passed=all(finding.passed for finding in findings),
            findings=findings,
            audited_artifact_names=sorted(artifact.name for artifact in artifacts),
            context_pack_count=pack_count,
            manuscript_section_count=manuscript_sections,
            artifact_count=len(artifacts),
        )

    def _chunk_identity_matches(self, source: ContextChunk, packed: ContextChunk) -> bool:
        return (
            source.model_dump(mode="json") == packed.model_dump(mode="json")
            and source.content_hash == self._text_hash(source.text)
            and packed.content_hash == self._text_hash(packed.text)
        )

    def _text_hash(self, text: str) -> str:
        return sha256_bytes(text.encode("utf-8"))
