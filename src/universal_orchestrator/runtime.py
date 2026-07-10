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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_records (
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    cache_key TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, task_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cancellations (
                    run_id TEXT PRIMARY KEY,
                    reason TEXT NOT NULL,
                    requested_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    cache_key TEXT,
                    warnings TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS failure_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
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

    def transition(self, run_id: str, state: str) -> None:
        from universal_orchestrator.models import utc_now

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO state_transitions(run_id, state, created_at) VALUES (?, ?, ?)",
                (run_id, state, utc_now().isoformat()),
            )

    def save_task_record(
        self,
        run_id: str,
        task_id: str,
        status: str,
        attempt: int,
        cache_key: str | None,
    ) -> None:
        from universal_orchestrator.models import utc_now

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO task_records(run_id, task_id, status, attempt, cache_key, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, task_id) DO UPDATE SET
                    status=excluded.status,
                    attempt=excluded.attempt,
                    cache_key=excluded.cache_key,
                    updated_at=excluded.updated_at
                """,
                (run_id, task_id, status, attempt, cache_key, utc_now().isoformat()),
            )

    def save_task_attempt(
        self,
        run_id: str,
        task_id: str,
        attempt: int,
        status: str,
        cache_key: str | None,
        warnings: list[str],
    ) -> None:
        from universal_orchestrator.models import utc_now

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO task_attempts(run_id, task_id, attempt, status, cache_key, warnings, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    task_id,
                    attempt,
                    status,
                    cache_key,
                    json.dumps(warnings),
                    utc_now().isoformat(),
                ),
            )

    def save_failure(self, run_id: str, stage: str, error: Exception) -> None:
        from universal_orchestrator.models import utc_now

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO failure_records(run_id, stage, error_type, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, stage, type(error).__name__, str(error), utc_now().isoformat()),
            )

    def latest_state(self, run_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state FROM state_transitions WHERE run_id=? ORDER BY id DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        return row[0] if row else None

    def resumable_snapshot(self, run_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_id, status, attempt, cache_key FROM task_records WHERE run_id=? ORDER BY task_id",
                (run_id,),
            ).fetchall()
        return {
            "run_id": run_id,
            "latest_state": self.latest_state(run_id),
            "cancel": self.cancel_status(run_id),
            "tasks": [
                {"task_id": row[0], "status": row[1], "attempt": row[2], "cache_key": row[3]}
                for row in rows
            ],
        }

    def request_cancel(self, run_id: str, reason: str = "User requested cancellation.") -> dict[str, Any]:
        from universal_orchestrator.models import RunState, RuntimeEvent, utc_now

        latest = self.latest_state(run_id)
        terminal_states = {RunState.DELIVERED, RunState.FAILED, RunState.CANCELLED}
        if latest in terminal_states or str(latest) in {str(state) for state in terminal_states}:
            return {
                "run_id": run_id,
                "accepted": False,
                "cancelled": False,
                "latest_state": latest,
                "reason": f"Run is already terminal: {latest}.",
            }
        requested_at = utc_now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cancellations(run_id, reason, requested_at)
                VALUES (?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    reason=excluded.reason,
                    requested_at=excluded.requested_at
                """,
                (run_id, reason, requested_at),
            )
        self.transition(run_id, RunState.CANCELLED)
        self.record_event(
            RuntimeEvent(
                run_id=run_id,
                event_type="cancel_requested",
                payload={"reason": reason, "requested_at": requested_at},
            )
        )
        return {
            "run_id": run_id,
            "accepted": True,
            "cancelled": True,
            "latest_state": RunState.CANCELLED,
            "reason": reason,
            "requested_at": requested_at,
        }

    def cancel_status(self, run_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT reason, requested_at FROM cancellations WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if not row:
            return {"requested": False}
        return {"requested": True, "reason": row[0], "requested_at": row[1]}

    def is_cancel_requested(self, run_id: str) -> bool:
        return self.cancel_status(run_id).get("requested", False)

    def clear_cancel(self, run_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cancellations WHERE run_id=?", (run_id,))

    def latest_successful_summary(self, exclude_run_id: str | None = None) -> dict[str, Any] | None:
        summaries = self.successful_summaries(exclude_run_id=exclude_run_id, limit=1)
        return summaries[0] if summaries else None

    def successful_summaries(
        self,
        exclude_run_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT run_id, state, artifact_dir, quality_passed, updated_at
            FROM run_summaries
            WHERE quality_passed=1
        """
        params: list[Any] = []
        if exclude_run_id:
            query += " AND run_id != ?"
            params.append(exclude_run_id)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "run_id": row[0],
                "state": row[1],
                "artifact_dir": row[2],
                "quality_passed": bool(row[3]),
                "updated_at": row[4],
            }
            for row in rows
        ]

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
