from __future__ import annotations

from html import escape
from pathlib import Path
import zipfile

from universal_orchestrator.models import Artifact, ArtifactType
from universal_orchestrator.utils import sha256_file


class ArtifactBuilder:
    def build_pdf(self, markdown: str, path: Path) -> Artifact:
        from reportlab.lib.pagesizes import A4  # type: ignore[import-not-found]
        from reportlab.lib.styles import getSampleStyleSheet  # type: ignore[import-not-found]
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer  # type: ignore[import-not-found]

        path.parent.mkdir(parents=True, exist_ok=True)
        styles = getSampleStyleSheet()
        story = []
        for line in markdown.splitlines():
            if not line.strip():
                story.append(Spacer(1, 8))
                continue
            if line.startswith("# "):
                style = styles["Heading1"]
            elif line.startswith("## "):
                style = styles["Heading2"]
            else:
                style = styles["BodyText"]
            text = line.lstrip("#").strip()
            story.append(Paragraph(escape(text), style))
            story.append(Spacer(1, 4))
        doc = SimpleDocTemplate(str(path), pagesize=A4, title="Universal Orchestrator Final Product")
        doc.build(story)
        return self._artifact(path, ArtifactType.PDF)

    def build_docx(self, markdown: str, path: Path) -> Artifact:
        from docx import Document  # type: ignore[import-not-found]

        path.parent.mkdir(parents=True, exist_ok=True)
        document = Document()
        for line in markdown.splitlines():
            if line.startswith("# "):
                document.add_heading(line[2:].strip(), level=1)
            elif line.startswith("## "):
                document.add_heading(line[3:].strip(), level=2)
            elif line.strip():
                document.add_paragraph(line.strip())
        document.save(path)
        return self._artifact(path, ArtifactType.DOCX)

    def validate_pdf(self, path: Path) -> list[str]:
        errors: list[str] = []
        try:
            from pypdf import PdfReader  # type: ignore[import-not-found]

            reader = PdfReader(str(path))
            if len(reader.pages) < 1:
                errors.append("PDF has no pages.")
        except Exception as exc:
            errors.append(f"PDF validation failed: {exc}")
        return errors

    def validate_docx(self, path: Path) -> list[str]:
        errors: list[str] = []
        try:
            from docx import Document  # type: ignore[import-not-found]

            document = Document(path)
            if not document.paragraphs:
                errors.append("DOCX has no paragraphs.")
        except Exception as exc:
            errors.append(f"DOCX validation failed: {exc}")
        return errors

    def build_patch_plan(self, markdown: str, path: Path) -> Artifact:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            "# Repository Patch Plan\n\n"
            "No repository changes were applied by this deterministic run. "
            "This file is a plan, not an implementation patch.\n\n"
            f"{markdown}"
        )
        path.write_text(content)
        return self._artifact(path, ArtifactType.REPORT)

    def validate_patch_plan(self, path: Path) -> list[str]:
        errors: list[str] = []
        if not path.exists():
            return ["Patch plan does not exist."]
        text = path.read_text(errors="replace")
        if not text.startswith("# Repository Patch Plan"):
            errors.append("Patch plan is missing its explicit plan heading.")
        if "not an implementation patch" not in text:
            errors.append("Patch plan does not disclose that no code patch was produced.")
        return errors

    def build_zip(self, artifacts: list[Artifact], path: Path) -> Artifact:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for artifact in sorted(artifacts, key=lambda item: item.name):
                artifact_path = artifact.as_path
                if artifact_path.exists() and artifact_path.resolve() != path.resolve():
                    archive.write(artifact_path, arcname=artifact_path.name)
        return self._artifact(path, ArtifactType.ZIP)

    def validate_zip(self, path: Path) -> list[str]:
        errors: list[str] = []
        if not path.exists():
            return ["ZIP file does not exist."]
        try:
            with zipfile.ZipFile(path) as archive:
                bad_member = archive.testzip()
                if bad_member:
                    errors.append(f"ZIP member failed CRC check: {bad_member}")
                if not archive.namelist():
                    errors.append("ZIP contains no files.")
        except Exception as exc:
            errors.append(f"ZIP validation failed: {exc}")
        return errors

    def _artifact(self, path: Path, artifact_type: ArtifactType) -> Artifact:
        return Artifact(
            type=artifact_type,
            name=path.name,
            path=str(path),
            content_hash=sha256_file(path),
            size_bytes=path.stat().st_size,
        )
