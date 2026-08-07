"""Audit logging for ontology action execution."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ontology_name: str = ""
    user_id: str = "anonymous"
    roles: list[str] = Field(default_factory=list)
    thread_id: str = ""
    action_name: str = ""
    target_type: str = ""
    target_id: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: str = ""  # success | failed | denied | approval_required | approved | rejected
    success: bool = False
    message: str = ""
    approved: bool = False


class AuditLogger:
    """Persist and query action audit logs."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._memory: list[AuditLogEntry] = []
        self.db_path = str(db_path) if db_path else None
        if self.db_path:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    ontology_name TEXT,
                    user_id TEXT,
                    roles TEXT,
                    thread_id TEXT,
                    action_name TEXT,
                    target_type TEXT,
                    target_id TEXT,
                    parameters TEXT,
                    status TEXT,
                    success INTEGER,
                    message TEXT,
                    approved INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action_name);
                CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
                CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp);
                """
            )

    def log(self, entry: AuditLogEntry) -> AuditLogEntry:
        self._memory.append(entry)
        if self.db_path:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO audit_logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        entry.id,
                        entry.timestamp,
                        entry.ontology_name,
                        entry.user_id,
                        json.dumps(entry.roles),
                        entry.thread_id,
                        entry.action_name,
                        entry.target_type,
                        entry.target_id,
                        json.dumps(entry.parameters, ensure_ascii=False),
                        entry.status,
                        int(entry.success),
                        entry.message,
                        int(entry.approved),
                    ),
                )
        return entry

    def query(
        self,
        action_name: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditLogEntry]:
        if self.db_path:
            query = "SELECT * FROM audit_logs WHERE 1=1"
            params: list = []
            if action_name:
                query += " AND action_name = ?"
                params.append(action_name)
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(query, params).fetchall()
            return [self._row_to_entry(r) for r in rows]

        results = list(reversed(self._memory))
        if action_name:
            results = [e for e in results if e.action_name == action_name]
        if user_id:
            results = [e for e in results if e.user_id == user_id]
        return results[:limit]

    def _row_to_entry(self, row: sqlite3.Row) -> AuditLogEntry:
        return AuditLogEntry(
            id=row["id"],
            timestamp=row["timestamp"],
            ontology_name=row["ontology_name"],
            user_id=row["user_id"],
            roles=json.loads(row["roles"]),
            thread_id=row["thread_id"],
            action_name=row["action_name"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            parameters=json.loads(row["parameters"]),
            status=row["status"],
            success=bool(row["success"]),
            message=row["message"],
            approved=bool(row["approved"]),
        )
