"""Ontology schema definitions (Palantir-inspired object model)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PropertyType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    ENUM = "enum"


class PropertyDef(BaseModel):
    name: str
    type: PropertyType = PropertyType.STRING
    required: bool = False
    enum_values: list[str] = Field(default_factory=list)
    description: str = ""


class ObjectTypeDef(BaseModel):
    """Defines an ontology object type (e.g. Person, Asset)."""

    name: str
    display_name: str = ""
    description: str = ""
    properties: list[PropertyDef] = Field(default_factory=list)
    primary_key: str = "id"

    def get_property(self, name: str) -> PropertyDef | None:
        return next((p for p in self.properties if p.name == name), None)


class LinkDef(BaseModel):
    """Defines a relationship between two object types."""

    name: str
    source_type: str
    target_type: str
    cardinality: str = "many"  # one | many
    description: str = ""


class ActionParamDef(BaseModel):
    name: str
    type: PropertyType = PropertyType.STRING
    required: bool = True
    description: str = ""


class ActionDef(BaseModel):
    """Defines an executable action on ontology objects."""

    name: str
    display_name: str = ""
    description: str = ""
    target_type: str
    parameters: list[ActionParamDef] = Field(default_factory=list)
    requires_approval: bool = False
    keywords: list[str] = Field(default_factory=list)
    allowed_roles: list[str] = Field(default_factory=list)
    approver_roles: list[str] = Field(default_factory=list)


class OntologyDef(BaseModel):
    """Complete ontology definition."""

    name: str
    version: str = "1.0"
    description: str = ""
    object_types: list[ObjectTypeDef] = Field(default_factory=list)
    links: list[LinkDef] = Field(default_factory=list)
    actions: list[ActionDef] = Field(default_factory=list)

    def get_object_type(self, name: str) -> ObjectTypeDef | None:
        return next((t for t in self.object_types if t.name == name), None)

    def get_action(self, name: str) -> ActionDef | None:
        return next((a for a in self.actions if a.name == name), None)

    def get_link(self, name: str) -> LinkDef | None:
        return next((l for l in self.links if l.name == name), None)


class OntologyObject(BaseModel):
    """Runtime instance of an ontology object."""

    object_type: str
    object_id: str
    properties: dict[str, Any] = Field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.properties.get(key, default)


class LinkInstance(BaseModel):
    """Runtime link between two objects."""

    link_type: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    success: bool
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    denied: bool = False
