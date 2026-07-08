from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from universal_orchestrator.ingestion.detectors import detect_input_type
from universal_orchestrator.models import (
    ContextManifest,
    HostInvocation,
    InputAttachment,
    InputRecord,
    InputStatus,
    InputType,
    new_id,
)
from universal_orchestrator.security import redact_text, scan_text
from universal_orchestrator.utils import compact_whitespace, iter_files, sha256_bytes, sha256_file, truncate_words


IGNORED_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
}


class InputIngestor:
    def __init__(self, max_file_bytes: int = 5_000_000, max_folder_files: int = 500) -> None:
        self.max_file_bytes = max_file_bytes
        self.max_folder_files = max_folder_files

    def ingest(self, invocation: HostInvocation, run_id: str) -> ContextManifest:
        records: list[InputRecord] = []
        warnings: list[str] = []

        prompt_findings = scan_text(invocation.prompt, location="prompt")
        prompt_text = redact_text(invocation.prompt)
        records.append(
            InputRecord(
                id="input_prompt",
                type=InputType.PROMPT,
                name="User prompt",
                uri="prompt://current",
                status=InputStatus.PARSED,
                content_hash=sha256_bytes(prompt_text.encode("utf-8")),
                summary=truncate_words(prompt_text, 120),
                metadata={"chars": len(prompt_text)},
                security_findings=prompt_findings,
            )
        )

        for attachment in invocation.attachments:
            try:
                records.append(self._ingest_attachment(attachment, invocation.cwd))
            except Exception as exc:  # pragma: no cover - defensive boundary
                warnings.append(f"Failed to ingest {attachment.uri}: {exc}")
                records.append(
                    InputRecord(
                        id=new_id("input"),
                        type=detect_input_type(attachment.uri),
                        name=attachment.name or Path(attachment.uri).name or attachment.uri,
                        uri=attachment.uri,
                        status=InputStatus.FAILED,
                        warnings=[str(exc)],
                    )
                )

        for link in invocation.links:
            if not any(item.uri == link for item in records):
                records.append(self._ingest_url(InputAttachment(uri=link), invocation.cwd))

        return ContextManifest(
            run_id=run_id,
            invocation_id=invocation.id,
            prompt={
                "raw": invocation.prompt,
                "parsed_intent": self._infer_prompt_intent(invocation.prompt),
                "quality": invocation.user_options.quality,
                "budget_profile": invocation.user_options.budget_profile,
            },
            inputs=records,
            warnings=warnings,
        )

    def _ingest_attachment(self, attachment: InputAttachment, cwd: str | None) -> InputRecord:
        input_type = detect_input_type(attachment.uri)
        if input_type in {InputType.URL, InputType.API}:
            return self._ingest_url(attachment, cwd)

        path = self._resolve_path(attachment.uri, cwd)
        name = attachment.name or path.name or str(path)
        if not path.exists():
            return InputRecord(
                id=new_id("input"),
                type=input_type,
                name=name,
                uri=attachment.uri,
                path=str(path),
                status=InputStatus.FAILED,
                warnings=["Path does not exist."],
            )

        if input_type in {InputType.FOLDER, InputType.REPO}:
            return self._ingest_folder(path, input_type, attachment)
        if input_type in {InputType.TEXT, InputType.MARKDOWN, InputType.CODE, InputType.UNKNOWN}:
            return self._ingest_text_file(path, input_type, attachment)
        if input_type == InputType.PDF:
            return self._ingest_pdf(path, attachment)
        return self._ingest_binary_metadata(path, input_type, attachment)

    def _resolve_path(self, uri: str, cwd: str | None) -> Path:
        path = Path(uri).expanduser()
        if not path.is_absolute() and cwd:
            path = Path(cwd).expanduser() / path
        return path.resolve()

    def _ingest_text_file(
        self, path: Path, input_type: InputType, attachment: InputAttachment
    ) -> InputRecord:
        size = path.stat().st_size
        warnings: list[str] = []
        if size > self.max_file_bytes:
            warnings.append(f"File exceeds max_file_bytes={self.max_file_bytes}; summary uses prefix only.")
        raw = path.read_bytes()[: self.max_file_bytes]
        text = raw.decode("utf-8", errors="replace")
        findings = scan_text(text, location=str(path))
        redacted = redact_text(text)
        return InputRecord(
            id=new_id("input"),
            type=input_type,
            name=attachment.name or path.name,
            uri=attachment.uri,
            path=str(path),
            status=InputStatus.PARSED,
            content_hash=sha256_file(path),
            size_bytes=size,
            mime_type=mimetypes.guess_type(path.name)[0],
            summary=truncate_words(redacted, 140),
            metadata={"chars_read": len(text), "suffix": path.suffix.lower()},
            warnings=warnings,
            security_findings=findings,
        )

    def _ingest_pdf(self, path: Path, attachment: InputAttachment) -> InputRecord:
        size = path.stat().st_size
        warnings: list[str] = []
        metadata: dict[str, object] = {"suffix": ".pdf"}
        text_parts: list[str] = []
        try:
            import pdfplumber  # type: ignore[import-not-found]

            with pdfplumber.open(path) as pdf:
                metadata["pages"] = len(pdf.pages)
                for index, page in enumerate(pdf.pages[:25], start=1):
                    page_text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                    if page_text:
                        text_parts.append(f"Page {index}: {page_text}")
                if len(pdf.pages) > 25:
                    warnings.append("PDF has more than 25 pages; MVP summary uses the first 25 pages.")
        except Exception as exc:  # pragma: no cover - depends on optional PDF runtime
            warnings.append(f"PDF text extraction unavailable: {exc}")

        text = "\n".join(text_parts)
        findings = scan_text(text, location=str(path))
        redacted = redact_text(text)
        status = InputStatus.PARSED if text_parts else InputStatus.PARTIAL
        return InputRecord(
            id=new_id("input"),
            type=InputType.PDF,
            name=attachment.name or path.name,
            uri=attachment.uri,
            path=str(path),
            status=status,
            content_hash=sha256_file(path),
            size_bytes=size,
            mime_type="application/pdf",
            summary=truncate_words(redacted, 180),
            metadata=metadata,
            warnings=warnings,
            security_findings=findings,
        )

    def _ingest_binary_metadata(
        self, path: Path, input_type: InputType, attachment: InputAttachment
    ) -> InputRecord:
        size = path.stat().st_size
        summary_by_type = {
            InputType.DOCX: "DOCX file detected; structured parsing is planned for the next parser milestone.",
            InputType.PPTX: "PPTX file detected; slide parsing is planned for the next parser milestone.",
            InputType.SPREADSHEET: "Spreadsheet detected; schema extraction is planned for the next parser milestone.",
            InputType.IMAGE: "Image detected; OCR and visual source cards are planned for the next parser milestone.",
            InputType.ARCHIVE: "Archive detected; sandbox unpacking is planned and not performed in this MVP.",
            InputType.AUDIO_VIDEO: "Media file detected; transcription is planned for a later milestone.",
        }
        status = InputStatus.PARTIAL if input_type in summary_by_type else InputStatus.PARSED
        return InputRecord(
            id=new_id("input"),
            type=input_type,
            name=attachment.name or path.name,
            uri=attachment.uri,
            path=str(path),
            status=status,
            content_hash=sha256_file(path),
            size_bytes=size,
            mime_type=mimetypes.guess_type(path.name)[0],
            summary=summary_by_type.get(input_type, f"{input_type} file detected."),
            metadata={"suffix": path.suffix.lower()},
            warnings=[] if status == InputStatus.PARSED else ["Structured parser not implemented yet."],
        )

    def _ingest_folder(
        self, path: Path, input_type: InputType, attachment: InputAttachment
    ) -> InputRecord:
        files = iter_files(path, IGNORED_NAMES, self.max_folder_files)
        suffix_counts: dict[str, int] = {}
        total_bytes = 0
        for file_path in files:
            suffix = file_path.suffix.lower() or "[none]"
            suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
            try:
                total_bytes += file_path.stat().st_size
            except OSError:
                pass
        warnings = []
        if len(files) >= self.max_folder_files:
            warnings.append(f"Folder scan capped at {self.max_folder_files} files.")
        summary = (
            f"Scanned {len(files)} files under {path.name}. "
            f"Common suffixes: {self._format_top_counts(suffix_counts)}."
        )
        metadata = {
            "files_scanned": len(files),
            "total_scanned_bytes": total_bytes,
            "suffix_counts": suffix_counts,
            "is_git_repo": (path / ".git").exists(),
        }
        return InputRecord(
            id=new_id("input"),
            type=input_type,
            name=attachment.name or path.name,
            uri=attachment.uri,
            path=str(path),
            status=InputStatus.PARSED,
            content_hash=sha256_bytes(compact_whitespace(str(metadata)).encode("utf-8")),
            size_bytes=total_bytes,
            summary=summary,
            metadata=metadata,
            warnings=warnings,
        )

    def _ingest_url(self, attachment: InputAttachment, cwd: str | None) -> InputRecord:
        del cwd
        input_type = detect_input_type(attachment.uri)
        parsed = urlparse(attachment.uri)
        return InputRecord(
            id=new_id("input"),
            type=input_type,
            name=attachment.name or parsed.netloc or attachment.uri,
            uri=attachment.uri,
            status=InputStatus.PARTIAL,
            content_hash=sha256_bytes(attachment.uri.encode("utf-8")),
            summary="URL recorded but not fetched because internet access requires explicit runtime permission.",
            metadata={"scheme": parsed.scheme, "netloc": parsed.netloc, "path": parsed.path},
            warnings=["URL fetch not performed in deterministic MVP."],
        )

    def _infer_prompt_intent(self, prompt: str) -> str:
        lowered = prompt.lower()
        if any(word in lowered for word in ["implement", "build", "code", "repo", "test"]):
            return "implementation"
        if any(word in lowered for word in ["report", "research", "pdf", "docx"]):
            return "research_and_artifact"
        if any(word in lowered for word in ["review", "audit", "critique"]):
            return "review_and_validation"
        return "orchestrated_task"

    def _format_top_counts(self, counts: dict[str, int]) -> str:
        if not counts:
            return "none"
        top = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
        return ", ".join(f"{suffix}={count}" for suffix, count in top)

