from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from universal_orchestrator.utils import ensure_dir, sha256_bytes


class SemanticCache:
    def __init__(self, root: Path | str) -> None:
        self.root = ensure_dir(Path(root))

    def key_for(self, namespace: str, payload: Any) -> str:
        data = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return f"{namespace}_{sha256_bytes(data).split(':', 1)[1]}"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self.root / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def set(self, key: str, value: dict[str, Any]) -> Path:
        path = self.root / f"{key}.json"
        ensure_dir(path.parent)
        path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")
        return path

