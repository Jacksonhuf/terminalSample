"""Admin API helpers for connector and credential management."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ontology_platform.connector.manager import ConnectorManager
from ontology_platform.connector.schema import CaptureSchedule, ConnectorDef, LoginConfig
from ontology_platform.connector.credential_store import CredentialStore
from ontology_platform.connector.store import ConnectorStore
from ontology_platform.mapping.store import MappingStore


class CreateCredentialRequest(BaseModel):
    name: str
    username: str
    password: str
    credential_id: str = ""
    login_url: str = ""
    notes: str = ""


class UpdateCredentialRequest(BaseModel):
    name: str | None = None
    username: str | None = None
    login_url: str | None = None
    notes: str | None = None


class RotatePasswordRequest(BaseModel):
    password: str


class SaveConnectorRequest(BaseModel):
    name: str
    description: str = ""
    mode: str = "computer_use"
    source_url: str = ""
    source_file: str = ""
    credential_ref: str = ""
    login: LoginConfig | None = None
    capture_instructions: str = ""
    computer_use_hints: list[str] = Field(default_factory=list)
    record_mappings: list[dict[str, Any]] = Field(default_factory=list)
    schedule: CaptureSchedule | None = None


class RunCaptureRequest(BaseModel):
    mock: bool = False
    auto_sync: bool = True


def connector_to_public(connector: ConnectorDef) -> dict[str, Any]:
    data = connector.model_dump(mode="json")
    data["mode"] = connector.mode.value
    return data


def build_connector_manager(
    connectors_dir: Path,
    connector_db_path: Path | None,
    credential_store: CredentialStore | None,
    mapping_store: MappingStore | None = None,
) -> ConnectorManager:
    store = ConnectorStore(connector_db_path or connectors_dir.parent / "connector.db")
    return ConnectorManager(connectors_dir, store, credential_store=credential_store, mapping_store=mapping_store)


def save_connector_from_request(
    manager: ConnectorManager,
    body: SaveConnectorRequest,
) -> ConnectorDef:
    from ontology_platform.connector.schema import CaptureMode, FieldMapping, RecordMapping

    mappings = []
    for item in body.record_mappings:
        field_mappings = [
            FieldMapping(**fm) for fm in item.get("field_mappings", [])
        ]
        mappings.append(
            RecordMapping(
                record_type=item["record_type"],
                object_type=item["object_type"],
                id_field=item.get("id_field", "id"),
                field_mappings=field_mappings,
            )
        )
    connector = ConnectorDef(
        name=body.name,
        description=body.description,
        mode=CaptureMode(body.mode),
        source_url=body.source_url,
        source_file=body.source_file,
        credential_ref=body.credential_ref,
        login=body.login,
        capture_instructions=body.capture_instructions,
        computer_use_hints=body.computer_use_hints,
        record_mappings=mappings,
        schedule=body.schedule,
    )
    manager.save_connector(connector)
    return connector
