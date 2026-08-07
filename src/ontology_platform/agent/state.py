"""LangGraph agent state definition."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


IntentType = Literal["query", "action", "traverse", "clarify", "unknown"]


class AgentState(TypedDict, total=False):
    """Shared state flowing through the agent graph."""

    messages: Annotated[list, add_messages]
    intent: IntentType
    entities: dict[str, Any]
    plan: list[dict[str, Any]]
    ontology_results: list[dict[str, Any]]
    requires_approval: bool
    approval_status: str  # "" | "approved" | "rejected"
    pending_action: dict[str, Any]
    interrupted: bool
    final_response: str
    error: str
