"""Admin API helpers for data mapping management."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ontology_platform.admin.manager import OntologyManager
from ontology_platform.connector.manager import ConnectorManager
from ontology_platform.connector.store import ConnectorStore
from ontology_platform.mapping.schema import FieldRule, ValueTransform
from ontology_platform.mapping.service import MappingService
from ontology_platform.mapping.store import MappingStore
from ontology_platform.ontology.service import OntologyService


class FieldRuleRequest(BaseModel):
    source: str
    target: str
    transform: ValueTransform = Field(default_factory=ValueTransform)


class SaveMappingProfileRequest(BaseModel):
    name: str
    connector_name: str
    record_type: str
    ontology_name: str
    object_type: str
    id_field: str = "id"
    source_id_field: str = "id"
    field_rules: list[FieldRuleRequest] = Field(default_factory=list)
    status: str = "draft"


class SyncMappingRequest(BaseModel):
    resync: bool = False
    run_id: str | None = None


def build_mapping_store(db_path: Path | None, fallback_dir: Path) -> MappingStore:
    path = db_path or fallback_dir.parent / "mapping.db"
    return MappingStore(path)


def build_mapping_service(
    mapping_store: MappingStore,
    connector_store: ConnectorStore,
) -> MappingService:
    return MappingService(mapping_store, connector_store)


def profile_to_dict(profile) -> dict[str, Any]:
    return profile.model_dump()


def get_ontology_object_types(manager: OntologyManager, ontology_name: str) -> list[dict[str, Any]]:
    ontology = manager.load(ontology_name)
    return [
        {
            "name": ot.name,
            "display_name": ot.display_name,
            "primary_key": ot.primary_key,
            "properties": [
                {
                    "name": p.name,
                    "type": p.type.value,
                    "required": p.required,
                    "enum_values": p.enum_values,
                }
                for p in ot.properties
            ],
        }
        for ot in ontology.object_types
    ]


def resolve_ontology_service(
    ontology_manager: OntologyManager,
    ontology_name: str,
    store_path: str | Path | None,
    database_url: str | None,
) -> OntologyService:
    from ontology_platform.agent.config import AgentConfig
    from ontology_platform.ontology.registry import OntologyRegistry
    from ontology_platform.ontology.store.factory import create_store

    ontology = ontology_manager.load(ontology_name)
    registry = OntologyRegistry()
    registry.register(ontology)
    config = AgentConfig(
        store_path=str(store_path) if store_path else None,
        database_url=database_url,
    )
    store = create_store(config)
    return OntologyService(registry, ontology_name, store=store)
