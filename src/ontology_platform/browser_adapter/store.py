"""SQLite persistence for generic browser sessions."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ontology_platform.browser_adapter.schema import SessionMode, SessionPublic, SessionStatus, StepResultPublic


class BrowserSessionStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS browser_sessions (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    start_url TEXT,
                    tab_policy TEXT DEFAULT 'reuse',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    steps_json TEXT NOT NULL DEFAULT '[]',
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    step_index INTEGER DEFAULT 0,
                    step_total INTEGER DEFAULT 0,
                    pending_command_json TEXT,
                    pending_command_id TEXT,
                    last_step_json TEXT,
                    step_version INTEGER DEFAULT 0,
                    collected_data_json TEXT NOT NULL DEFAULT '[]',
                    error TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    last_heartbeat_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_browser_sessions_status
                    ON browser_sessions(status);
                """
            )

    def create_session(
        self,
        *,
        mode: SessionMode,
        start_url: str = "",
        tab_policy: str = "reuse",
        metadata: dict[str, Any] | None = None,
        steps: list[dict[str, Any]] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> SessionPublic:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        steps_list = steps or []
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO browser_sessions (
                    id, status, mode, start_url, tab_policy, metadata_json,
                    steps_json, parameters_json, step_index, step_total, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    session_id,
                    "pending",
                    mode,
                    start_url,
                    tab_policy,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    json.dumps(steps_list, ensure_ascii=False),
                    json.dumps(parameters or {}, ensure_ascii=False),
                    len(steps_list),
                    now,
                ),
            )
        return self.get_session(session_id)  # type: ignore[return-value]

    def get_session(self, session_id: str) -> SessionPublic | None:
        row = self.get_row(session_id)
        if row is None:
            return None
        return self._to_public(row)

    def get_row(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM browser_sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None

    def list_pending(self, limit: int = 20) -> list[SessionPublic]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM browser_sessions
                WHERE status IN ('pending', 'running', 'waiting_extension')
                ORDER BY started_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._to_public(r) for r in rows]

    def update_session(self, session_id: str, **fields: Any) -> None:
        if not fields:
            return
        allowed = {
            "status",
            "step_index",
            "step_total",
            "steps_json",
            "parameters_json",
            "metadata_json",
            "pending_command_json",
            "pending_command_id",
            "last_step_json",
            "step_version",
            "collected_data_json",
            "error",
            "finished_at",
            "last_heartbeat_at",
        }
        parts: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            parts.append(f"{key}=?")
            values.append(value)
        if not parts:
            return
        values.append(session_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE browser_sessions SET {', '.join(parts)} WHERE id=?", values)

    def heartbeat(self, session_id: str) -> None:
        self.update_session(
            session_id,
            last_heartbeat_at=datetime.now(timezone.utc).isoformat(),
        )

    def _to_public(self, row: sqlite3.Row) -> SessionPublic:
        collected = json.loads(row["collected_data_json"] or "[]")
        last_step = None
        if row["last_step_json"]:
            last_step = StepResultPublic.model_validate(json.loads(row["last_step_json"]))
        return SessionPublic(
            id=row["id"],
            status=row["status"],  # type: ignore[arg-type]
            mode=row["mode"],  # type: ignore[arg-type]
            start_url=row["start_url"] or "",
            tab_policy=row["tab_policy"] or "reuse",  # type: ignore[arg-type]
            metadata=json.loads(row["metadata_json"] or "{}"),
            step_index=row["step_index"],
            step_total=row["step_total"],
            data_count=len(collected),
            error=row["error"] or "",
            started_at=row["started_at"],
            finished_at=row["finished_at"] or "",
            last_step=last_step,
        )
