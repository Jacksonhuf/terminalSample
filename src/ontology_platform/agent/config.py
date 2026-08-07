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
    store_path: str | None = None  # SQLite path; None = in-memory
    thread_id: str = "default"

    def use_sqlite(self) -> bool:
        return self.store_path is not None
