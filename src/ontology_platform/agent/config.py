"""Agent configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

PlannerMode = Literal["rule", "llm", "auto"]
StoreBackend = Literal["auto", "memory", "sqlite", "postgres"]


@dataclass
class AgentConfig:
    """Configuration for the ontology agent platform."""

    planner_mode: PlannerMode = "rule"
    enable_approval_flow: bool = True
    enable_governance: bool = True
    store_backend: StoreBackend = "auto"
    store_path: str | None = None  # SQLite path; None = in-memory
    database_url: str | None = None  # PostgreSQL URL
    audit_path: str | None = None  # Audit log SQLite; defaults to store_path
    integrations_db_path: str | None = None  # Message log + outreach; defaults to store_path
    checkpoint_path: str | None = None  # LangGraph checkpoint SQLite; defaults near store_path
    thread_id: str = "default"
    user_id: str = "anonymous"
    roles: list[str] = field(default_factory=lambda: ["operator"])

    def use_sqlite(self) -> bool:
        return self.resolve_store_backend() == "sqlite"

    def use_postgres(self) -> bool:
        return self.resolve_store_backend() == "postgres"

    def resolve_store_backend(self) -> StoreBackend:
        if self.store_backend != "auto":
            return self.store_backend
        if self.database_url and self.database_url.startswith("postgres"):
            return "postgres"
        if self.store_path:
            return "sqlite"
        return "memory"

    def get_audit_path(self) -> str | None:
        return self.audit_path or self.store_path

    def get_checkpoint_path(self) -> str | None:
        if self.checkpoint_path:
            return self.checkpoint_path
        if self.store_path:
            base = Path(self.store_path)
            return str(base.with_name(f"{base.stem}.checkpoints.db"))
        return None
