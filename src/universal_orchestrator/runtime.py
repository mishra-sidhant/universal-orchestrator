from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from universal_orchestrator.models import RuntimeEvent
from universal_orchestrator.utils import ensure_dir


class RuntimeStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        ensure_dir(self.path.parent)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_summaries (
                    run_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    artifact_dir TEXT NOT NULL,
                    quality_passed INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def record_event(self, event: RuntimeEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events(run_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
                (
                    event.run_id,
                    event.event_type,
                    json.dumps(event.payload, sort_keys=True, default=str),
                    event.created_at.isoformat(),
                ),
            )

    def save_run_summary(self, run_id: str, state: str, artifact_dir: str, quality_passed: bool) -> None:
        from universal_orchestrator.models import utc_now

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO run_summaries(run_id, state, artifact_dir, quality_passed, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    state=excluded.state,
                    artifact_dir=excluded.artifact_dir,
                    quality_passed=excluded.quality_passed,
                    updated_at=excluded.updated_at
                """,
                (run_id, state, artifact_dir, int(quality_passed), utc_now().isoformat()),
            )

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT run_id, event_type, payload, created_at FROM events WHERE run_id=? ORDER BY id",
                (run_id,),
            ).fetchall()
        return [
            {
                "run_id": row[0],
                "event_type": row[1],
                "payload": json.loads(row[2]),
                "created_at": row[3],
            }
            for row in rows
        ]

