"""LangGraph graph builder for ontology agents."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ontology_platform.agent.nodes import (
    make_executor_node,
    make_planner_node,
    make_response_node,
    make_router_node,
)
from ontology_platform.agent.state import AgentState
from ontology_platform.agent.tools import create_ontology_tools
from ontology_platform.ontology.service import OntologyService


def _route_by_intent(state: AgentState) -> str:
    intent = state.get("intent", "unknown")
    if intent == "clarify":
        return "clarify"
    if intent in ("query", "action", "traverse"):
        return "plan"
    return "clarify"


def build_agent_graph(service: OntologyService, checkpointer=None):
    """Build a minimal LangGraph agent that operates on an ontology.

    Graph flow:
        START -> router -> planner -> executor -> respond -> END
                      └-> clarify -> respond -> END
    """
    tools = create_ontology_tools(service)
    tools_by_name = {t.name: t for t in tools}

    graph = StateGraph(AgentState)

    graph.add_node("router", make_router_node(service))
    graph.add_node("planner", make_planner_node(service))
    graph.add_node("executor", make_executor_node(tools_by_name))
    graph.add_node("respond", make_response_node(service))

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        _route_by_intent,
        {"plan": "planner", "clarify": "respond"},
    )
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "respond")
    graph.add_edge("respond", END)

    return graph.compile(checkpointer=checkpointer)
