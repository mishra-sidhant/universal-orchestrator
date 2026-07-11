from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()) * 4 // 3) if text else 0


def compact_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def truncate_words(text: str, limit: int = 80) -> str:
    words = compact_whitespace(text).split()
    if len(words) <= limit:
        return " ".join(words)
    return " ".join(words[:limit]) + "..."


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    serialized = json.dumps(payload, indent=2, sort_keys=True, default=json_default) + "\n"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def iter_files(root: Path, ignored_names: Iterable[str], max_files: int) -> list[Path]:
    ignored = set(ignored_names)
    files: list[Path] = []
    for current_root, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name not in ignored and not name.startswith(".uo")]
        for name in names:
            if name in ignored:
                continue
            path = Path(current_root) / name
            files.append(path)
            if len(files) >= max_files:
                return files
    return files
