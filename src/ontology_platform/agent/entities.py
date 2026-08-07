"""Entity extraction helpers for planners and agents."""

from __future__ import annotations

import re
from typing import Any

from ontology_platform.ontology.service import OntologyService


def extract_filters(text: str) -> dict[str, Any]:
    """Extract property filters from natural language."""
    filters: dict[str, Any] = {}
    text_lower = text.lower()
    if any(kw in text_lower for kw in ["可用", "available", "空闲"]):
        filters["status"] = "available"
    elif any(kw in text_lower for kw in ["使用中", "in_use", "在用"]):
        filters["status"] = "in_use"
    elif any(kw in text_lower for kw in ["维修", "maintenance"]):
        filters["status"] = "maintenance"
    elif any(kw in text_lower for kw in ["报废", "retired"]):
        filters["status"] = "retired"
    model_match = re.search(r"\b(X\d{3})\b", text, re.IGNORECASE)
    if model_match:
        filters["model"] = model_match.group(1).upper()
    return filters


def extract_entities(text: str, service: OntologyService) -> dict[str, Any]:
    """Rule-based entity extraction."""
    entities: dict[str, Any] = {}
    text_lower = text.lower()
    entities["filters"] = extract_filters(text)

    for obj_type in service.ontology.object_types:
        names = [obj_type.name.lower(), obj_type.display_name.lower()]
        if any(n and n in text_lower for n in names):
            entities["object_type"] = obj_type.name

    type_aliases = {
        "样机": "Prototype",
        "原型机": "Prototype",
        "设备": "Prototype",
    }
    for alias, type_name in type_aliases.items():
        if alias in text and service.ontology.get_object_type(type_name):
            entities["object_type"] = type_name

    id_match = re.search(
        r"\b(SN-\d{4}-\d{3}|[A-Z]{2,}-\d{4}-\d{3,}|\w+-\d+)\b",
        text,
        re.IGNORECASE,
    )
    if id_match:
        entities["object_id"] = id_match.group(1).upper()
        if entities["object_id"].startswith("SN-") and service.ontology.get_object_type("Prototype"):
            entities["object_type"] = "Prototype"

    for action in service.ontology.actions:
        keywords = [
            action.name.lower(),
            action.display_name.lower(),
            *[k.lower() for k in action.keywords],
        ]
        if any(kw and kw in text_lower for kw in keywords):
            entities["action_name"] = action.name

    for link in service.ontology.links:
        if link.name.lower() in text_lower:
            entities["link_type"] = link.name

    return entities
