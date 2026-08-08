"""Extra LangChain tools for the prototype app."""

from __future__ import annotations

import json

from langchain_core.tools import StructuredTool

from ontology_platform.apps.prototype_analytics import build_dashboard
from ontology_platform.ontology.service import OntologyService


def create_prototype_tools(service: OntologyService) -> list[StructuredTool]:
    def get_prototype_dashboard() -> str:
        dashboard = build_dashboard(service)
        return json.dumps(dashboard, ensure_ascii=False, indent=2)

    return [
        StructuredTool.from_function(
            func=get_prototype_dashboard,
            name="get_prototype_dashboard",
            description="Get prototype inventory dashboard: counts by status/model, in-use, overdue reservations",
        ),
    ]
