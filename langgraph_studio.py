"""LangGraph Studio entry point for debugging the ontology agent graph.

Usage:
    pip install -e ".[studio]"
    langgraph dev

Opens LangGraph Studio UI for step-by-step graph debugging.
"""

from __future__ import annotations

from pathlib import Path

from ontology_platform.agent.config import AgentConfig
from ontology_platform.apps.prototype import PrototypeApp

EXAMPLES = Path(__file__).parent / "examples"

# Graph exported for LangGraph Studio
_config = AgentConfig(enable_governance=False, enable_approval_flow=True)
_app = PrototypeApp.create(EXAMPLES / "prototype_ontology.yaml", config=_config)
_app.seed()
graph = _app.platform.graph
