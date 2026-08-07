"""SQLite store for scheduled outreach / reminder tasks."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ontology_platform.integrations.schema import ChannelType, OutreachTask


class OutreachStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._memory: list[OutreachTask] = []
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
                CREATE TABLE IF NOT EXISTS outreach_tasks (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    recipients TEXT NOT NULL,
                    subject TEXT,
                    context TEXT,
                    object_type TEXT,
                    object_id TEXT,
                    person_id TEXT,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    created_by_action TEXT,
                    audit_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_outreach_due
                    ON outreach_tasks(status, due_at);
                CREATE INDEX IF NOT EXISTS idx_outreach_object
                    ON outreach_tasks(object_type, object_id, status);
                """
            )

    def create_task(
        self,
        *,
        channel: ChannelType,
        template_id: str,
        recipients: list[str],
        due_at: str,
        context: dict[str, Any] | None = None,
        subject: str = "",
        object_type: str = "",
        object_id: str = "",
        person_id: str = "",
        created_by_action: str = "",
        audit_id: str = "",
    ) -> OutreachTask:
        task = OutreachTask(
            id=str(uuid.uuid4()),
            channel=channel,
            template_id=template_id,
            recipients=recipients,
            subject=subject,
            context=context or {},
            object_type=object_type,
            object_id=object_id,
            person_id=person_id,
            due_at=due_at,
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by_action=created_by_action,
            audit_id=audit_id,
        )
        self._persist(task)
        return task

    def _persist(self, task: OutreachTask) -> None:
        self._memory = [t for t in self._memory if t.id != task.id]
        self._memory.append(task)
        if self.db_path:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO outreach_tasks VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        task.id,
                        task.channel.value,
                        task.template_id,
                        json.dumps(task.recipients, ensure_ascii=False),
                        task.subject,
                        json.dumps(task.context, ensure_ascii=False),
                        task.object_type,
                        task.object_id,
                        task.person_id,
                        task.due_at,
                        task.status,
                        task.attempt_count,
                        task.last_error,
                        task.created_at,
                        task.created_by_action,
                        task.audit_id,
                    ),
                )

    def list_due(self, *, now: str | None = None, limit: int = 100) -> list[OutreachTask]:
        now_iso = now or datetime.now(timezone.utc).isoformat()
        if self.db_path:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM outreach_tasks
                    WHERE status='pending' AND due_at <= ?
                    ORDER BY due_at LIMIT ?
                    """,
                    (now_iso, limit),
                ).fetchall()
            return [self._row_to_task(r) for r in rows]

        return [
            t
            for t in self._memory
            if t.status == "pending" and t.due_at <= now_iso
        ][:limit]

    def list_tasks(
        self,
        *,
        object_type: str | None = None,
        object_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[OutreachTask]:
        if self.db_path:
            query = "SELECT * FROM outreach_tasks WHERE 1=1"
            params: list = []
            if object_type:
                query += " AND object_type = ?"
                params.append(object_type)
            if object_id:
                query += " AND object_id = ?"
                params.append(object_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY due_at DESC LIMIT ?"
            params.append(limit)
            with self._connect() as conn:
                rows = conn.execute(query, params).fetchall()
            return [self._row_to_task(r) for r in rows]

        results = list(self._memory)
        if object_type:
            results = [t for t in results if t.object_type == object_type]
        if object_id:
            results = [t for t in results if t.object_id == object_id]
        if status:
            results = [t for t in results if t.status == status]
        return sorted(results, key=lambda t: t.due_at, reverse=True)[:limit]

    def update_task(self, task: OutreachTask) -> None:
        self._persist(task)

    def cancel_pending(
        self,
        *,
        object_type: str,
        object_id: str,
        template_id: str | None = None,
    ) -> int:
        cancelled = 0
        if self.db_path:
            query = """
                UPDATE outreach_tasks SET status='cancelled'
                WHERE status='pending' AND object_type=? AND object_id=?
            """
            params: list = [object_type, object_id]
            if template_id:
                query += " AND template_id=?"
                params.append(template_id)
            with self._connect() as conn:
                cur = conn.execute(query, params)
                cancelled = cur.rowcount
        else:
            for task in self._memory:
                if (
                    task.status == "pending"
                    and task.object_type == object_type
                    and task.object_id == object_id
                    and (template_id is None or task.template_id == template_id)
                ):
                    task.status = "cancelled"
                    cancelled += 1
        return cancelled

    def _row_to_task(self, row: sqlite3.Row) -> OutreachTask:
        return OutreachTask(
            id=row["id"],
            channel=ChannelType(row["channel"]),
            template_id=row["template_id"],
            recipients=json.loads(row["recipients"] or "[]"),
            subject=row["subject"] or "",
            context=json.loads(row["context"] or "{}"),
            object_type=row["object_type"] or "",
            object_id=row["object_id"] or "",
            person_id=row["person_id"] or "",
            due_at=row["due_at"],
            status=row["status"],
            attempt_count=row["attempt_count"] or 0,
            last_error=row["last_error"] or "",
            created_at=row["created_at"] or "",
            created_by_action=row["created_by_action"] or "",
            audit_id=row["audit_id"] or "",
        )
