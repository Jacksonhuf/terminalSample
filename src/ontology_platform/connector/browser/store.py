"""SQLite persistence for browser extension runs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ontology_platform.connector.browser.schema import BrowserDriveMode, BrowserRunStatus, BrowserRunPublic


class BrowserRunStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS browser_runs (
                    id TEXT PRIMARY KEY,
                    connector_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    drive_mode TEXT NOT NULL,
                    action_name TEXT,
                    source_url TEXT,
                    connector_run_id TEXT,
                    step_index INTEGER DEFAULT 0,
                    step_total INTEGER DEFAULT 0,
                    steps_json TEXT NOT NULL DEFAULT '[]',
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    collected_records_json TEXT NOT NULL DEFAULT '[]',
                    auto_sync INTEGER DEFAULT 1,
                    records_captured INTEGER DEFAULT 0,
                    error TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    last_heartbeat_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_browser_runs_status
                    ON browser_runs(status);
                """
            )

    def create_run(
        self,
        *,
        connector_name: str,
        drive_mode: BrowserDriveMode,
        action_name: str = "",
        source_url: str = "",
        steps: list[dict[str, Any]] | None = None,
        parameters: dict[str, Any] | None = None,
        auto_sync: bool = True,
    ) -> BrowserRunPublic:
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        steps_list = steps or []
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO browser_runs (
                    id, connector_name, status, drive_mode, action_name, source_url,
                    step_index, step_total, steps_json, parameters_json, auto_sync, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    connector_name,
                    BrowserRunStatus.PENDING.value,
                    drive_mode,
                    action_name,
                    source_url,
                    len(steps_list),
                    json.dumps(steps_list, ensure_ascii=False),
                    json.dumps(parameters or {}, ensure_ascii=False),
                    int(auto_sync),
                    now,
                ),
            )
        return self.get_run(run_id)  # type: ignore[return-value]

    def get_run(self, run_id: str) -> BrowserRunPublic | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM browser_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        return self._to_public(row)

    def get_run_row(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM browser_runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_pending(self, limit: int = 20) -> list[BrowserRunPublic]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM browser_runs
                WHERE status IN ('pending', 'running')
                ORDER BY started_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._to_public(r) for r in rows]

    def update_run(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return
        allowed = {
            "status",
            "connector_run_id",
            "step_index",
            "step_total",
            "steps_json",
            "collected_records_json",
            "records_captured",
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
        values.append(run_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE browser_runs SET {', '.join(parts)} WHERE id=?", values)

    def heartbeat(self, run_id: str) -> None:
        self.update_run(
            run_id,
            last_heartbeat_at=datetime.now(timezone.utc).isoformat(),
        )

    def _to_public(self, row: sqlite3.Row) -> BrowserRunPublic:
        return BrowserRunPublic(
            id=row["id"],
            connector_name=row["connector_name"],
            status=BrowserRunStatus(row["status"]),
            drive_mode=row["drive_mode"],  # type: ignore[arg-type]
            action_name=row["action_name"] or "",
            source_url=row["source_url"] or "",
            connector_run_id=row["connector_run_id"] or "",
            step_index=row["step_index"],
            step_total=row["step_total"],
            records_captured=row["records_captured"],
            error=row["error"] or "",
            started_at=row["started_at"],
            finished_at=row["finished_at"] or "",
        )
