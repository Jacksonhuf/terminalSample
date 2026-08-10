"""Tests for data mapping: staging → ontology mapping profiles."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_platform.admin.server import create_app
from ontology_platform.connector.manager import ConnectorManager
from ontology_platform.connector.schema import CaptureBatch
from ontology_platform.connector.store import ConnectorStore
from ontology_platform.mapping.schema import FieldRule
from ontology_platform.mapping.service import MappingService
from ontology_platform.mapping.store import MappingStore
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
def mapping_store(tmp_path: Path) -> MappingStore:
    return MappingStore(tmp_path / "mapping.db")


@pytest.fixture
def ontology_service(tmp_path: Path) -> OntologyService:
    registry = OntologyRegistry.from_yaml(ONTOLOGY_YAML)
    return OntologyService(registry, "prototype", store=SQLiteStore(str(tmp_path / "prototype.db")))


@pytest.fixture
def manager(
    connector_store: ConnectorStore,
    mapping_store: MappingStore,
    ontology_service: OntologyService,
) -> ConnectorManager:
    return ConnectorManager(
        CONNECTOR_DIR,
        connector_store,
        ontology_service,
        mapping_store=mapping_store,
    )


@pytest.fixture
def mapping_service(mapping_store: MappingStore, connector_store: ConnectorStore) -> MappingService:
    return MappingService(mapping_store, connector_store)


@pytest.fixture
def admin_client(tmp_path: Path) -> TestClient:
    app = create_app(
        ontology_dir=EXAMPLES,
        store_path=tmp_path / "platform.db",
        ontology_yaml_path=ONTOLOGY_YAML,
        connectors_dir=CONNECTOR_DIR,
        connector_db_path=tmp_path / "connector.db",
        mapping_db_path=tmp_path / "mapping.db",
    )
    return TestClient(app)


class TestMappingStore:
    def test_create_and_activate_profile(self, mapping_store: MappingStore):
        p1 = mapping_store.create_profile(
            name="Map A",
            connector_name="prototype_erp",
            record_type="prototype",
            ontology_name="prototype",
            object_type="Prototype",
            field_rules=[FieldRule(source="id", target="id")],
        )
        p2 = mapping_store.create_profile(
            name="Map B",
            connector_name="prototype_erp",
            record_type="prototype",
            ontology_name="prototype",
            object_type="Prototype",
            field_rules=[FieldRule(source="id", target="id")],
        )
        mapping_store.activate_profile(p1.id)
        active = mapping_store.activate_profile(p2.id)
        assert active.status == "active"
        p1_updated = mapping_store.get_profile(p1.id)
        assert p1_updated is not None
        assert p1_updated.status == "archived"


class TestMappingService:
    def test_staging_summary_after_ingest(self, manager: ConnectorManager, mapping_service: MappingService):
        data = json.loads(SAMPLE_CAPTURE.read_text(encoding="utf-8"))
        manager.ingest_batch(CaptureBatch.model_validate(data))
        summaries = mapping_service.list_staging_summary()
        assert any(s.record_type == "prototype" for s in summaries)
        assert any(s.record_type == "project" for s in summaries)

    def test_preview_mapping(self, manager: ConnectorManager, mapping_service: MappingService, mapping_store: MappingStore):
        data = json.loads(SAMPLE_CAPTURE.read_text(encoding="utf-8"))
        manager.ingest_batch(CaptureBatch.model_validate(data))
        profile = mapping_store.create_profile(
            name="Prototype map",
            connector_name="prototype_erp",
            record_type="prototype",
            ontology_name="prototype",
            object_type="Prototype",
            field_rules=[
                FieldRule(source="id", target="id"),
                FieldRule(source="serial_number", target="serial_number"),
                FieldRule(source="model", target="model"),
                FieldRule(source="status", target="status"),
            ],
        )
        previews = mapping_service.preview(profile, limit=3)
        assert len(previews) == 2
        assert previews[0].mapped_properties.get("serial_number")

    def test_sync_via_active_profile(
        self,
        manager: ConnectorManager,
        mapping_service: MappingService,
        mapping_store: MappingStore,
        ontology_service: OntologyService,
    ):
        data = json.loads(SAMPLE_CAPTURE.read_text(encoding="utf-8"))
        ingest = manager.ingest_batch(CaptureBatch.model_validate(data))
        profile = mapping_store.create_profile(
            name="Prototype map",
            connector_name="prototype_erp",
            record_type="prototype",
            ontology_name="prototype",
            object_type="Prototype",
            field_rules=[
                FieldRule(source="id", target="id"),
                FieldRule(source="serial_number", target="serial_number"),
                FieldRule(source="model", target="model"),
                FieldRule(source="status", target="status"),
            ],
            status="active",
        )
        mapping_store.activate_profile(profile.id)
        result = mapping_service.sync_profile(profile.id, ontology_service)
        assert result["synced"] == 2
        obj = ontology_service.get_object("Prototype", "P-101")
        assert obj is not None
        assert obj.properties["model"] == "Alpha-X1"

    def test_connector_manager_prefers_active_profile(
        self,
        manager: ConnectorManager,
        mapping_store: MappingStore,
        ontology_service: OntologyService,
    ):
        data = json.loads(SAMPLE_CAPTURE.read_text(encoding="utf-8"))
        ingest = manager.ingest_batch(CaptureBatch.model_validate(data))
        profile = mapping_store.create_profile(
            name="Custom map",
            connector_name="prototype_erp",
            record_type="prototype",
            ontology_name="prototype",
            object_type="Prototype",
            field_rules=[
                FieldRule(source="id", target="id"),
                FieldRule(source="serial_number", target="serial_number"),
                FieldRule(source="model", target="model"),
                FieldRule(source="status", target="status"),
            ],
        )
        mapping_store.activate_profile(profile.id)
        result = manager.sync_to_ontology("prototype_erp", run_id=ingest["run_id"])
        assert result["synced"] >= 2
        assert ontology_service.get_object("Prototype", "P-101") is not None


class TestMappingAdminApi:
    def test_staging_and_profile_crud(self, admin_client: TestClient, manager: ConnectorManager):
        data = json.loads(SAMPLE_CAPTURE.read_text(encoding="utf-8"))
        manager.ingest_batch(CaptureBatch.model_validate(data))

        staging = admin_client.get("/api/mappings/staging")
        assert staging.status_code == 200
        assert staging.json()["count"] >= 1

        create = admin_client.post(
            "/api/mappings/profiles",
            json={
                "name": "ERP Prototype",
                "connector_name": "prototype_erp",
                "record_type": "prototype",
                "ontology_name": "prototype",
                "object_type": "Prototype",
                "field_rules": [
                    {"source": "id", "target": "id"},
                    {"source": "serial_number", "target": "serial_number"},
                    {"source": "model", "target": "model"},
                    {"source": "status", "target": "status"},
                ],
                "status": "draft",
            },
        )
        assert create.status_code == 200
        profile_id = create.json()["id"]

        preview = admin_client.post(f"/api/mappings/profiles/{profile_id}/preview?limit=2")
        assert preview.status_code == 200
        assert len(preview.json()["previews"]) == 2

        activate = admin_client.post(f"/api/mappings/profiles/{profile_id}/activate")
        assert activate.status_code == 200
        assert activate.json()["status"] == "active"

        sync = admin_client.post(f"/api/mappings/profiles/{profile_id}/sync", json={"resync": False})
        assert sync.status_code == 200
        assert sync.json()["synced"] == 2

    def test_mappings_page(self, admin_client: TestClient):
        resp = admin_client.get("/admin/integration/mappings/discover", follow_redirects=False)
        assert resp.status_code == 200
        assert "Ontology Platform" in resp.text
        assert "shell.js" in resp.text
