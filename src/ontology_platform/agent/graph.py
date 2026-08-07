"""LangGraph graph builder for ontology agents."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from ontology_platform.agent.config import AgentConfig
from ontology_platform.agent.nodes import (
    make_approval_node,
    make_executor_node,
    make_plan_node,
    make_response_node,
)
from ontology_platform.agent.planner import Planner, RulePlanner
from ontology_platform.agent.state import AgentState
from ontology_platform.agent.tools import create_ontology_tools
from ontology_platform.ontology.service import OntologyService


def _route_after_execute(state: AgentState, enable_approval: bool) -> str:
    if (
        enable_approval
        and state.get("requires_approval")
        and state.get("approval_status") not in ("approved", "rejected")
    ):
        return "approval"
    if state.get("approval_status") == "approved":
        return "execute_approved"
    return "respond"


def _route_after_approval(state: AgentState) -> str:
    if state.get("approval_status") == "approved":
        return "execute_approved"
    return "respond"


def build_agent_graph(
    service: OntologyService,
    planner: Planner | None = None,
    config: AgentConfig | None = None,
    checkpointer=None,
):
    """Build a LangGraph agent that operates on an ontology.

    Graph flow:
        START -> plan -> execute -> [approval] -> execute_approved -> respond -> END
    """
    cfg = config or AgentConfig()
    planner = planner or RulePlanner()
    tools = create_ontology_tools(service)
    tools_by_name = {t.name: t for t in tools}

    graph = StateGraph(AgentState)

    graph.add_node("plan", make_plan_node(service, planner))
    graph.add_node("execute", make_executor_node(tools_by_name, approved=False))
    graph.add_node("approval", make_approval_node())
    graph.add_node("execute_approved", make_executor_node(tools_by_name, approved=True))
    graph.add_node("respond", make_response_node(service))

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "execute")
    graph.add_conditional_edges(
        "execute",
        lambda s: _route_after_execute(s, cfg.enable_approval_flow),
        {"approval": "approval", "execute_approved": "execute_approved", "respond": "respond"},
    )
    graph.add_conditional_edges(
        "approval",
        _route_after_approval,
        {"execute_approved": "execute_approved", "respond": "respond"},
    )
    graph.add_edge("execute_approved", "respond")
    graph.add_edge("respond", END)

    saver = checkpointer if checkpointer is not None else MemorySaver()
    return graph.compile(checkpointer=saver)
