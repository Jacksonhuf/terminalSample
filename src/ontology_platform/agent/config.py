"""Agent configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PlannerMode = Literal["rule", "llm", "auto"]


@dataclass
class AgentConfig:
    """Configuration for the ontology agent platform."""

    planner_mode: PlannerMode = "rule"
    enable_approval_flow: bool = True
    enable_governance: bool = True
    store_path: str | None = None  # SQLite path; None = in-memory
    audit_path: str | None = None  # Audit log SQLite; defaults to store_path
    thread_id: str = "default"
    user_id: str = "anonymous"
    roles: list[str] = field(default_factory=lambda: ["operator"])

    def use_sqlite(self) -> bool:
        return self.store_path is not None

    def get_audit_path(self) -> str | None:
        return self.audit_path or self.store_path
