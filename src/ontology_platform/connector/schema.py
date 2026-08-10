"""Data connector schema — Computer Use capture and SQL staging."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CaptureMode(str, Enum):
    COMPUTER_USE = "computer_use"
    API = "api"
    FILE = "file"


class FieldMapping(BaseModel):
    """Map a raw payload field to an ontology property."""

    source: str
    target: str


class RecordMapping(BaseModel):
    """Map captured record type to ontology object type."""

    record_type: str
    object_type: str
    id_field: str = "id"
    field_mappings: list[FieldMapping] = Field(default_factory=list)


class LoginConfig(BaseModel):
    """Login flow hints for Computer Use (credentials stored separately)."""

    type: str = "form"
    login_url: str = ""
    username_field: str = "username"
    password_field: str = "password"
    post_login_wait: str = ""


class CaptureSchedule(BaseModel):
    """Optional periodic capture schedule for a connector."""

    enabled: bool = False
    interval_sec: int = 3600
    auto_sync: bool = True


class ConnectorDef(BaseModel):
    """Definition of a data connector (Palantir Pipeline / Data Connection inspired)."""

    name: str
    description: str = ""
    mode: CaptureMode = CaptureMode.COMPUTER_USE
    source_url: str = ""
    source_file: str = ""
    credential_ref: str = ""
    login: LoginConfig | None = None
    capture_instructions: str = ""
    record_mappings: list[RecordMapping] = Field(default_factory=list)
    computer_use_hints: list[str] = Field(default_factory=list)
    schedule: CaptureSchedule | None = None


class CaptureRecord(BaseModel):
    """One record captured by Computer Use or other sources."""

    record_type: str
    external_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaptureBatch(BaseModel):
    """Batch of records from a single Computer Use run."""

    connector: str
    run_id: str | None = None
    source_url: str = ""
    records: list[CaptureRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionRun(BaseModel):
    id: str
    connector_name: str
    status: str  # pending | running | completed | failed
    mode: str
    source_url: str = ""
    started_at: str = ""
    finished_at: str = ""
    records_captured: int = 0
    records_synced: int = 0
    error: str = ""


class StagedRecord(BaseModel):
    id: str
    run_id: str
    connector_name: str
    record_type: str
    external_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    synced: bool = False
    ontology_object_id: str = ""
