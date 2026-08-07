"""Execution context for governed ontology actions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExecutionContext:
    """Who is executing an action and in which conversation."""

    user_id: str = "anonymous"
    roles: list[str] = field(default_factory=lambda: ["operator"])
    thread_id: str = "default"

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def is_admin(self) -> bool:
        return "admin" in self.roles

    def is_viewer(self) -> bool:
        return self.roles == ["viewer"] or (len(self.roles) == 1 and self.has_role("viewer"))
