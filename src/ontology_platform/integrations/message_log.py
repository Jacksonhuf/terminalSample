"""SQLite store for outbound message delivery logs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ontology_platform.integrations.schema import MessageLogEntry


class MessageLogStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._memory: list[MessageLogEntry] = []
        self.db_path = str(db_path) if db_path else None
        if self.db_path:
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
                CREATE TABLE IF NOT EXISTS message_logs (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    template_id TEXT,
                    recipients TEXT,
                    subject TEXT,
                    body TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    object_type TEXT,
                    object_id TEXT,
                    correlation_id TEXT,
                    created_by TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_message_logs_object
                    ON message_logs(object_type, object_id);
                CREATE INDEX IF NOT EXISTS idx_message_logs_time
                    ON message_logs(timestamp);
                """
            )

    def append(
        self,
        *,
        channel: str,
        template_id: str,
        recipients: list[str],
        subject: str,
        body: str,
        status: str,
        error: str = "",
        object_type: str = "",
        object_id: str = "",
        correlation_id: str = "",
        created_by: str = "",
    ) -> MessageLogEntry:
        entry = MessageLogEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            channel=channel,
            template_id=template_id,
            recipients=recipients,
            subject=subject,
            body=body,
            status=status,
            error=error,
            object_type=object_type,
            object_id=object_id,
            correlation_id=correlation_id,
            created_by=created_by,
        )
        self._memory.append(entry)
        if self.db_path:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO message_logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        entry.id,
                        entry.timestamp,
                        entry.channel,
                        entry.template_id,
                        json.dumps(entry.recipients, ensure_ascii=False),
                        entry.subject,
                        entry.body,
                        entry.status,
                        entry.error,
                        entry.object_type,
                        entry.object_id,
                        entry.correlation_id,
                        entry.created_by,
                    ),
                )
        return entry

    def query(
        self,
        object_type: str | None = None,
        object_id: str | None = None,
        limit: int = 100,
    ) -> list[MessageLogEntry]:
        if self.db_path:
            query = "SELECT * FROM message_logs WHERE 1=1"
            params: list = []
            if object_type:
                query += " AND object_type = ?"
                params.append(object_type)
            if object_id:
                query += " AND object_id = ?"
                params.append(object_id)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            with self._connect() as conn:
                rows = conn.execute(query, params).fetchall()
            return [self._row_to_entry(r) for r in rows]

        results = list(reversed(self._memory))
        if object_type:
            results = [e for e in results if e.object_type == object_type]
        if object_id:
            results = [e for e in results if e.object_id == object_id]
        return results[:limit]

    def _row_to_entry(self, row: sqlite3.Row) -> MessageLogEntry:
        return MessageLogEntry(
            id=row["id"],
            timestamp=row["timestamp"],
            channel=row["channel"],
            template_id=row["template_id"] or "",
            recipients=json.loads(row["recipients"] or "[]"),
            subject=row["subject"] or "",
            body=row["body"] or "",
            status=row["status"],
            error=row["error"] or "",
            object_type=row["object_type"] or "",
            object_id=row["object_id"] or "",
            correlation_id=row["correlation_id"] or "",
            created_by=row["created_by"] or "",
        )
