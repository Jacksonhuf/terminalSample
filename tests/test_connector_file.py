"""Connector FILE 模式测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ontology_platform.connector.manager import ConnectorManager
from ontology_platform.connector.schema import ConnectorDef, RecordMapping, FieldMapping
from ontology_platform.connector.store import ConnectorStore
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.service import OntologyService
from ontology_platform.ontology.store.sqlite import SQLiteStore

EXAMPLES = Path(__file__).parent.parent / "examples"
CONNECTOR_DIR = EXAMPLES / "connectors"
ONTOLOGY_YAML = EXAMPLES / "prototype_ontology.yaml"


@pytest.fixture
def connector_store(tmp_path: Path) -> ConnectorStore:
    return ConnectorStore(tmp_path / "connector.db")


@pytest.fixture
def ontology_service(tmp_path: Path) -> OntologyService:
    registry = OntologyRegistry.from_yaml(ONTOLOGY_YAML)
    return OntologyService(registry, "prototype", store=SQLiteStore(str(tmp_path / "prototype.db")))


def _write_file_connector(tmp_path: Path, data_file: Path) -> Path:
    connector_dir = tmp_path / "connectors"
    connector_dir.mkdir()
    config = {
        "name": "test_file",
        "description": "test",
        "mode": "file",
        "source_file": str(data_file),
        "record_mappings": [
            {
                "record_type": "prototype",
                "object_type": "Prototype",
                "id_field": "id",
                "field_mappings": [
                    {"source": "id", "target": "id"},
                    {"source": "serial_number", "target": "serial_number"},
                    {"source": "model", "target": "model"},
                    {"source": "status", "target": "status"},
                ],
            }
        ],
    }
    yaml_path = connector_dir / "test_file.yaml"
    import yaml

    yaml_path.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")
    return connector_dir


def test_file_connector_ingest(tmp_path: Path, connector_store: ConnectorStore, ontology_service: OntologyService) -> None:
    data_file = tmp_path / "prototypes.json"
    data_file.write_text(
        json.dumps(
            [
                {"id": "p1", "serial_number": "SN-1", "model": "M1", "status": "available"},
                {"id": "p2", "serial_number": "SN-2", "model": "M2", "status": "in_use"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    connector_dir = _write_file_connector(tmp_path, data_file)
    manager = ConnectorManager(connector_dir, connector_store, ontology_service)
    result = manager.ingest_file("test_file")
    assert result["created"] == 2
    assert result["updated"] == 0
    assert len(ontology_service.search_objects("Prototype")) == 2


def test_file_connector_updates_existing(
    tmp_path: Path, connector_store: ConnectorStore, ontology_service: OntologyService
) -> None:
    data_file = tmp_path / "prototypes.json"
    data_file.write_text(
        json.dumps([{"id": "p1", "serial_number": "SN-1", "model": "M1", "status": "available"}]),
        encoding="utf-8",
    )
    connector_dir = _write_file_connector(tmp_path, data_file)
    manager = ConnectorManager(connector_dir, connector_store, ontology_service)
    manager.ingest_file("test_file")
    data_file.write_text(
        json.dumps([{"id": "p1", "serial_number": "SN-1", "model": "M1", "status": "in_use"}]),
        encoding="utf-8",
    )
    result = manager.ingest_file("test_file")
    assert result["updated"] == 1
    obj = ontology_service.get_object("Prototype", "p1")
    assert obj is not None
    assert obj.properties["status"] == "in_use"


def test_load_prototype_file_connector(
    connector_store: ConnectorStore, ontology_service: OntologyService
) -> None:
    manager = ConnectorManager(CONNECTOR_DIR, connector_store, ontology_service)
    connector = manager.load_connector("prototype_file")
    assert connector.mode.value == "file"
    assert connector.source_file.endswith("prototype_seed.json")
