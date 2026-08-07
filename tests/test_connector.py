"""Tests for data connector: Computer Use → SQL → Ontology."""

import json
from pathlib import Path

import pytest

from ontology_platform.connector.manager import ConnectorManager
from ontology_platform.connector.schema import CaptureBatch, CaptureRecord
from ontology_platform.connector.store import ConnectorStore
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.service import OntologyService
from ontology_platform.ontology.store.sqlite import SQLiteStore

EXAMPLES = Path(__file__).parent.parent / "examples"
CONNECTOR_DIR = EXAMPLES / "connectors"
ONTOLOGY_YAML = EXAMPLES / "prototype_ontology.yaml"
SAMPLE_CAPTURE = EXAMPLES / "captures" / "prototype_erp_sample.json"


@pytest.fixture
def connector_store(tmp_path: Path) -> ConnectorStore:
    return ConnectorStore(tmp_path / "connector.db")


@pytest.fixture
def ontology_service(tmp_path: Path) -> OntologyService:
    registry = OntologyRegistry.from_yaml(ONTOLOGY_YAML)
    return OntologyService(registry, "prototype", store=SQLiteStore(str(tmp_path / "prototype.db")))


@pytest.fixture
def manager(connector_store: ConnectorStore, ontology_service: OntologyService) -> ConnectorManager:
    return ConnectorManager(CONNECTOR_DIR, connector_store, ontology_service)


class TestConnectorDef:
    def test_load_connector(self, manager: ConnectorManager):
        connector = manager.load_connector("prototype_erp")
        assert connector.name == "prototype_erp"
        assert connector.mode.value == "computer_use"
        assert len(connector.record_mappings) == 2

    def test_list_connectors(self, manager: ConnectorManager):
        names = manager.list_connectors()
        assert "prototype_erp" in names


class TestIngestion:
    def test_ingest_sample_capture(self, manager: ConnectorManager, connector_store: ConnectorStore):
        data = json.loads(SAMPLE_CAPTURE.read_text(encoding="utf-8"))
        batch = CaptureBatch.model_validate(data)
        result = manager.ingest_batch(batch)
        assert result["records_staged"] == 3
        run = connector_store.get_run(result["run_id"])
        assert run is not None
        assert run.records_captured == 3

    def test_ingest_with_explicit_run_id(self, manager: ConnectorManager):
        run_id = manager.start_run("prototype_erp")
        batch = CaptureBatch(
            connector="prototype_erp",
            run_id=run_id,
            records=[
                CaptureRecord(
                    record_type="prototype",
                    external_id="P-999",
                    payload={
                        "id": "P-999",
                        "serial_number": "SN-999",
                        "model": "Test",
                        "status": "available",
                    },
                )
            ],
        )
        result = manager.ingest_batch(batch)
        assert result["run_id"] == run_id
        assert result["records_staged"] == 1


class TestSync:
    def test_sync_to_ontology(self, manager: ConnectorManager, ontology_service: OntologyService):
        data = json.loads(SAMPLE_CAPTURE.read_text(encoding="utf-8"))
        batch = CaptureBatch.model_validate(data)
        ingest = manager.ingest_batch(batch)
        result = manager.sync_to_ontology("prototype_erp", run_id=ingest["run_id"])
        assert result["synced"] == 3
        assert result["errors"] == []

        proto = ontology_service.get_object("Prototype", "P-101")
        assert proto is not None
        assert proto.properties["serial_number"] == "SN-2026-101"
        assert proto.properties["model"] == "Alpha-X1"

        project = ontology_service.get_object("Project", "PRJ-1")
        assert project is not None
        assert project.properties["name"] == "Project Alpha"


class TestComputerUseTask:
    def test_get_task(self, manager: ConnectorManager):
        task = manager.get_computer_use_task("prototype_erp")
        assert task["connector"] == "prototype_erp"
        assert task["run_id"]
        assert "prototype" in task["expected_record_types"]
        assert "records" in task["output_format"]
