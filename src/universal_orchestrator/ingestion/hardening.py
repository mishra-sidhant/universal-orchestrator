from __future__ import annotations

from pathlib import Path


class IngestionLimits:
    def __init__(
        self,
        max_file_bytes: int = 5_000_000,
        max_folder_files: int = 500,
        max_archive_entries: int = 2_000,
        max_archive_uncompressed_bytes: int = 100_000_000,
    ) -> None:
        self.max_file_bytes = max_file_bytes
        self.max_folder_files = max_folder_files
        self.max_archive_entries = max_archive_entries
        self.max_archive_uncompressed_bytes = max_archive_uncompressed_bytes


def detect_text_encoding(raw: bytes) -> str:
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return "utf-16"
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def symlink_warning(path: Path) -> str | None:
    if path.is_symlink():
        return "Path is a symlink; target was resolved before ingestion."
    return None
