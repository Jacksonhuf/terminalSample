"""Schema for staging-data → ontology mapping profiles."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ValueTransform(BaseModel):
    """Optional value transformation when mapping a field."""

    type: str = "direct"  # direct | map | default
    mapping: dict[str, str] = Field(default_factory=dict)
    default: str | None = None


class FieldRule(BaseModel):
    """Map a source payload field to an ontology property."""

    source: str
    target: str
    transform: ValueTransform = Field(default_factory=ValueTransform)


class MappingProfile(BaseModel):
    """Configuration binding staged records to an ontology object type."""

    id: str
    name: str
    connector_name: str
    record_type: str
    ontology_name: str
    object_type: str
    id_field: str = "id"
    source_id_field: str = "id"
    field_rules: list[FieldRule] = Field(default_factory=list)
    status: str = "draft"  # draft | active | archived
    created_at: str = ""
    updated_at: str = ""


class SyncRunLog(BaseModel):
    """Audit log for a mapping sync execution."""

    id: str
    profile_id: str
    connector_name: str = ""
    record_type: str = ""
    started_at: str = ""
    finished_at: str = ""
    status: str = "running"  # running | completed | failed
    records_processed: int = 0
    records_synced: int = 0
    records_failed: int = 0
    errors: list[str] = Field(default_factory=list)
    resync: bool = False


class StagedSummary(BaseModel):
    """Aggregated view of staged data for discovery UI."""

    connector_name: str
    record_type: str
    total: int = 0
    unsynced: int = 0
    synced: int = 0
    sample_fields: list[str] = Field(default_factory=list)


class PreviewResult(BaseModel):
    """Result of a dry-run mapping preview."""

    source_external_id: str
    mapped_properties: dict[str, Any] = Field(default_factory=dict)
    object_id: str = ""
    errors: list[str] = Field(default_factory=list)
