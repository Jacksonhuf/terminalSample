"""Connector manager: load definitions, ingest captures, sync to ontology."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ontology_platform.connector.schema import (
    CaptureBatch,
    ConnectorDef,
    FieldMapping,
    RecordMapping,
)
from ontology_platform.connector.store import ConnectorStore
from ontology_platform.ontology.service import OntologyService


class ConnectorManager:
    """Orchestrate Computer Use data capture → SQL → Ontology sync."""

    def __init__(
        self,
        connector_dir: str | Path,
        store: ConnectorStore,
        ontology_service: OntologyService | None = None,
    ) -> None:
        self.connector_dir = Path(connector_dir)
        self.store = store
        self.ontology_service = ontology_service

    def load_connector(self, name: str) -> ConnectorDef:
        path = self.connector_dir / f"{name}.yaml"
        if not path.exists():
            # search by connector name field inside yaml files
            for yaml_path in self.connector_dir.glob("*.yaml"):
                with open(yaml_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data.get("name") == name:
                    return ConnectorDef.model_validate(data)
            raise FileNotFoundError(f"Connector not found: {name}")
        with open(path, encoding="utf-8") as f:
            return ConnectorDef.model_validate(yaml.safe_load(f))

    def list_connectors(self) -> list[str]:
        names = []
        for path in sorted(self.connector_dir.glob("*.yaml")):
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            names.append(data.get("name", path.stem))
        return names

    def start_run(self, connector_name: str) -> str:
        connector = self.load_connector(connector_name)
        run = self.store.create_run(
            connector_name=connector.name,
            mode=connector.mode.value,
            source_url=connector.source_url,
        )
        return run.id

    def ingest_batch(self, batch: CaptureBatch) -> dict[str, Any]:
        """Ingest Computer Use capture results into SQL staging tables."""
        connector = self.load_connector(batch.connector)
        run_id = batch.run_id or self.start_run(batch.connector)

        for record in batch.records:
            self.store.stage_record(
                run_id=run_id,
                connector_name=connector.name,
                record_type=record.record_type,
                external_id=record.external_id,
                payload=record.payload,
            )

        self.store.complete_run(
            run_id,
            status="completed",
            records_captured=len(batch.records),
        )
        return {"run_id": run_id, "records_staged": len(batch.records)}

    def sync_to_ontology(
        self,
        connector_name: str,
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Map staged SQL records into ontology objects."""
        if self.ontology_service is None:
            raise ValueError("OntologyService required for sync")

        connector = self.load_connector(connector_name)
        mapping_index = {m.record_type: m for m in connector.record_mappings}
        staged = self.store.list_unsynced(connector_name)

        if run_id:
            staged = [s for s in staged if s.run_id == run_id]

        synced = 0
        errors: list[str] = []

        for record in staged:
            mapping = mapping_index.get(record.record_type)
            if mapping is None:
                errors.append(f"No mapping for record_type: {record.record_type}")
                continue
            try:
                properties = self._apply_mapping(record.payload, mapping)
                object_id = str(properties.get(mapping.id_field, record.external_id))
                existing = self.ontology_service.get_object(mapping.object_type, object_id)
                if existing:
                    props = dict(existing.properties)
                    props.update(properties)
                    from ontology_platform.ontology.schema import OntologyObject

                    self.ontology_service.store.update_object(
                        OntologyObject(
                            object_type=mapping.object_type,
                            object_id=object_id,
                            properties=props,
                        )
                    )
                else:
                    self.ontology_service.create_object(
                        mapping.object_type, properties, object_id=object_id
                    )
                self.store.mark_synced(record.id, object_id)
                synced += 1
            except Exception as exc:
                errors.append(f"{record.external_id}: {exc}")

        if run_id:
            run = self.store.get_run(run_id)
            if run:
                self.store.complete_run(
                    run_id,
                    status="completed" if not errors else "completed",
                    records_captured=run.records_captured,
                    records_synced=synced,
                )

        return {"synced": synced, "errors": errors}

    def get_computer_use_task(self, connector_name: str) -> dict[str, Any]:
        """Build instructions for a Computer Use agent to execute capture."""
        connector = self.load_connector(connector_name)
        run_id = self.start_run(connector_name)
        return {
            "run_id": run_id,
            "connector": connector.name,
            "source_url": connector.source_url,
            "mode": connector.mode.value,
            "instructions": connector.capture_instructions,
            "hints": connector.computer_use_hints,
            "expected_record_types": [m.record_type for m in connector.record_mappings],
            "output_format": {
                "connector": connector.name,
                "run_id": run_id,
                "records": [
                    {
                        "record_type": "<record_type>",
                        "external_id": "<unique_id>",
                        "payload": {"field": "value"},
                    }
                ],
            },
        }

    def _apply_mapping(self, payload: dict, mapping: RecordMapping) -> dict[str, Any]:
        if not mapping.field_mappings:
            return dict(payload)
        result: dict[str, Any] = {}
        for fm in mapping.field_mappings:
            if fm.source in payload:
                result[fm.target] = payload[fm.source]
        if mapping.id_field not in result and mapping.id_field in payload:
            result[mapping.id_field] = payload[mapping.id_field]
        return result
