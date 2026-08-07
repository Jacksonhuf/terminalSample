"""Persistent approval request queue for the approval workbench."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ApprovalRequest(BaseModel):
    id: str
    thread_id: str
    status: str  # pending | approved | rejected
    action_name: str = ""
    target_type: str = ""
    target_id: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    requester_id: str = ""
    requester_roles: list[str] = Field(default_factory=list)
    created_at: str = ""
    resolved_at: str = ""
    resolver_id: str = ""
    resolver_roles: list[str] = Field(default_factory=list)
    message: str = ""


class ApprovalStore:
    """Track pending and resolved approval requests."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._memory: list[ApprovalRequest] = []
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
                CREATE TABLE IF NOT EXISTS approval_requests (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    action_name TEXT,
                    target_type TEXT,
                    target_id TEXT,
                    parameters TEXT,
                    requester_id TEXT,
                    requester_roles TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    resolver_id TEXT,
                    resolver_roles TEXT,
                    message TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_approval_status ON approval_requests(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_approval_thread ON approval_requests(thread_id);
                """
            )

    def create_pending(
        self,
        *,
        thread_id: str,
        action_name: str,
        target_id: str,
        parameters: dict[str, Any] | None = None,
        requester_id: str = "",
        requester_roles: list[str] | None = None,
        message: str = "",
        target_type: str = "",
    ) -> ApprovalRequest:
        existing = self.get_pending_by_thread(thread_id)
        if existing is not None:
            return existing

        request = ApprovalRequest(
            id=str(uuid.uuid4()),
            thread_id=thread_id,
            status="pending",
            action_name=action_name,
            target_type=target_type,
            target_id=target_id,
            parameters=parameters or {},
            requester_id=requester_id,
            requester_roles=requester_roles or [],
            created_at=datetime.now(timezone.utc).isoformat(),
            message=message,
        )
        self._persist(request)
        return request

    def resolve(
        self,
        request_id: str,
        *,
        approved: bool,
        resolver_id: str = "",
        resolver_roles: list[str] | None = None,
    ) -> ApprovalRequest | None:
        request = self.get(request_id)
        if request is None or request.status != "pending":
            return None
        request.status = "approved" if approved else "rejected"
        request.resolved_at = datetime.now(timezone.utc).isoformat()
        request.resolver_id = resolver_id
        request.resolver_roles = resolver_roles or []
        self._persist(request)
        return request

    def resolve_by_thread(
        self,
        thread_id: str,
        *,
        approved: bool,
        resolver_id: str = "",
        resolver_roles: list[str] | None = None,
    ) -> ApprovalRequest | None:
        request = self.get_pending_by_thread(thread_id)
        if request is None:
            return None
        return self.resolve(
            request.id,
            approved=approved,
            resolver_id=resolver_id,
            resolver_roles=resolver_roles,
        )

    def get(self, request_id: str) -> ApprovalRequest | None:
        if self.db_path:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM approval_requests WHERE id = ?",
                    (request_id,),
                ).fetchone()
            return self._row_to_request(row) if row else None
        return next((r for r in self._memory if r.id == request_id), None)

    def get_pending_by_thread(self, thread_id: str) -> ApprovalRequest | None:
        items = self.list_requests(status="pending", thread_id=thread_id, limit=1)
        return items[0] if items else None

    def list_requests(
        self,
        *,
        status: str | None = None,
        thread_id: str | None = None,
        limit: int = 100,
    ) -> list[ApprovalRequest]:
        if self.db_path:
            query = "SELECT * FROM approval_requests WHERE 1=1"
            params: list = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if thread_id:
                query += " AND thread_id = ?"
                params.append(thread_id)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            with self._connect() as conn:
                rows = conn.execute(query, params).fetchall()
            return [self._row_to_request(r) for r in rows]

        results = list(self._memory)
        if status:
            results = [r for r in results if r.status == status]
        if thread_id:
            results = [r for r in results if r.thread_id == thread_id]
        return sorted(results, key=lambda r: r.created_at, reverse=True)[:limit]

    def _persist(self, request: ApprovalRequest) -> None:
        self._memory = [r for r in self._memory if r.id != request.id]
        self._memory.append(request)
        if self.db_path:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO approval_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        request.id,
                        request.thread_id,
                        request.status,
                        request.action_name,
                        request.target_type,
                        request.target_id,
                        json.dumps(request.parameters, ensure_ascii=False),
                        request.requester_id,
                        json.dumps(request.requester_roles, ensure_ascii=False),
                        request.created_at,
                        request.resolved_at,
                        request.resolver_id,
                        json.dumps(request.resolver_roles, ensure_ascii=False),
                        request.message,
                    ),
                )

    def _row_to_request(self, row: sqlite3.Row) -> ApprovalRequest:
        return ApprovalRequest(
            id=row["id"],
            thread_id=row["thread_id"],
            status=row["status"],
            action_name=row["action_name"] or "",
            target_type=row["target_type"] or "",
            target_id=row["target_id"] or "",
            parameters=json.loads(row["parameters"] or "{}"),
            requester_id=row["requester_id"] or "",
            requester_roles=json.loads(row["requester_roles"] or "[]"),
            created_at=row["created_at"] or "",
            resolved_at=row["resolved_at"] or "",
            resolver_id=row["resolver_id"] or "",
            resolver_roles=json.loads(row["resolver_roles"] or "[]"),
            message=row["message"] or "",
        )
