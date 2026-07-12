from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from universal_orchestrator.models import InputType


TEXT_SUFFIXES = {".txt", ".rst", ".log"}
MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdx"}
CODE_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".cs",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".swift",
    ".kt",
    ".scala",
    ".sh",
    ".zsh",
    ".bash",
    ".sql",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg"}
SPREADSHEET_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls", ".ods"}
ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z"}
AUDIO_VIDEO_SUFFIXES = {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".avi", ".mkv", ".webm"}


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def detect_input_type(uri: str) -> InputType:
    if is_url(uri):
        url_path = urlparse(uri).path.lower()
        if "/api/" in url_path or url_path.endswith(".json"):
            return InputType.API
        return InputType.URL

    path = Path(uri).expanduser()
    suffix = path.suffix.lower()

    if path.is_dir():
        return InputType.REPO if (path / ".git").exists() else InputType.FOLDER
    if suffix in MARKDOWN_SUFFIXES:
        return InputType.MARKDOWN
    if suffix in TEXT_SUFFIXES:
        return InputType.TEXT
    if suffix == ".pdf":
        return InputType.PDF
    if suffix == ".docx":
        return InputType.DOCX
    if suffix == ".pptx":
        return InputType.PPTX
    if suffix in SPREADSHEET_SUFFIXES:
        return InputType.SPREADSHEET
    if suffix in IMAGE_SUFFIXES:
        return InputType.IMAGE
    if suffix in ARCHIVE_SUFFIXES:
        return InputType.ARCHIVE
    if suffix in AUDIO_VIDEO_SUFFIXES:
        return InputType.AUDIO_VIDEO
    if suffix in CODE_SUFFIXES:
        return InputType.CODE
    return InputType.UNKNOWN
