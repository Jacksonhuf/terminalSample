"""LangChain tools wrapping OntologyService."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ontology_platform.ontology.service import OntologyService


class SearchObjectsInput(BaseModel):
    object_type: str = Field(description="Ontology object type name")
    filters: dict[str, Any] = Field(default_factory=dict, description="Property filters")
    limit: int = Field(default=20, description="Max results")


class GetObjectInput(BaseModel):
    object_type: str
    object_id: str


class TraverseLinksInput(BaseModel):
    object_type: str
    object_id: str
    link_type: str | None = None
    direction: str = Field(default="outgoing", description="outgoing or incoming")


class ExecuteActionInput(BaseModel):
    action_name: str
    target_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False


def create_ontology_tools(service: OntologyService) -> list[StructuredTool]:
    """Create LangChain tools from an OntologyService instance."""

    def search_objects(object_type: str, filters: dict | None = None, limit: int = 20) -> str:
        results = service.search_objects(object_type, filters or {}, limit)
        return json.dumps([r.model_dump() for r in results], ensure_ascii=False, indent=2)

    def get_object(object_type: str, object_id: str) -> str:
        obj = service.get_object(object_type, object_id)
        if obj is None:
            return json.dumps({"error": "Object not found"}, ensure_ascii=False)
        return json.dumps(obj.model_dump(), ensure_ascii=False, indent=2)

    def traverse_links(
        object_type: str,
        object_id: str,
        link_type: str | None = None,
        direction: str = "outgoing",
    ) -> str:
        results = service.traverse_links(object_type, object_id, link_type, direction)
        return json.dumps(results, ensure_ascii=False, indent=2)

    def execute_action(
        action_name: str,
        target_id: str,
        parameters: dict | None = None,
        approved: bool = False,
    ) -> str:
        result = service.execute_action(action_name, target_id, parameters or {}, approved)
        return json.dumps(result.model_dump(), ensure_ascii=False, indent=2)

    def get_schema() -> str:
        return json.dumps(service.get_schema_summary(), ensure_ascii=False, indent=2)

    return [
        StructuredTool.from_function(
            func=search_objects,
            name="search_objects",
            description="Search ontology objects by type and property filters",
            args_schema=SearchObjectsInput,
        ),
        StructuredTool.from_function(
            func=get_object,
            name="get_object",
            description="Get a single ontology object by type and ID",
            args_schema=GetObjectInput,
        ),
        StructuredTool.from_function(
            func=traverse_links,
            name="traverse_links",
            description="Traverse links from an object to find related objects",
            args_schema=TraverseLinksInput,
        ),
        StructuredTool.from_function(
            func=execute_action,
            name="execute_action",
            description="Execute an ontology action on a target object",
            args_schema=ExecuteActionInput,
        ),
        StructuredTool.from_function(
            func=get_schema,
            name="get_ontology_schema",
            description="Get the ontology schema summary including types, links, and actions",
        ),
    ]
