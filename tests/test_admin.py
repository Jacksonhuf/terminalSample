"""Tests for ontology admin UI."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_platform.admin.manager import OntologyManager
from ontology_platform.admin.server import create_app
from ontology_platform.ontology.schema import (
    ActionDef,
    LinkDef,
    ObjectTypeDef,
    OntologyDef,
    PropertyDef,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def manager(temp_dir):
    return OntologyManager(temp_dir)


@pytest.fixture
def sample_ontology():
    return OntologyDef(
        name="test_ont",
        description="Test ontology",
        object_types=[
            ObjectTypeDef(
                name="Asset",
                display_name="资产",
                properties=[
                    PropertyDef(name="id", type="string", required=True),
                    PropertyDef(name="name", type="string", required=True),
                ],
            ),
            ObjectTypeDef(name="Person", display_name="人员", properties=[]),
        ],
        links=[
            LinkDef(name="owns", source_type="Person", target_type="Asset"),
        ],
        actions=[
            ActionDef(name="Transfer", target_type="Asset", requires_approval=True),
        ],
    )


@pytest.fixture
def client(temp_dir, sample_ontology):
    mgr = OntologyManager(temp_dir)
    mgr.save(sample_ontology)
    app = create_app(temp_dir)
    return TestClient(app)


class TestOntologyManager:
    def test_create_and_load(self, manager, sample_ontology):
        manager.create(sample_ontology)
        loaded = manager.load("test_ont")
        assert loaded.name == "test_ont"
        assert len(loaded.object_types) == 2

    def test_list_ontologies(self, manager, sample_ontology):
        manager.create(sample_ontology)
        items = manager.list_ontologies()
        assert len(items) == 1
        assert items[0]["name"] == "test_ont"

    def test_save_updates(self, manager, sample_ontology):
        manager.create(sample_ontology)
        sample_ontology.description = "Updated"
        manager.save(sample_ontology)
        assert manager.load("test_ont").description == "Updated"

    def test_delete(self, manager, sample_ontology):
        manager.create(sample_ontology)
        assert manager.delete("test_ont") is True
        with pytest.raises(FileNotFoundError):
            manager.load("test_ont")

    def test_to_graph(self, manager, sample_ontology):
        manager.create(sample_ontology)
        graph = manager.to_graph("test_ont")
        assert len(graph["nodes"]) == 3  # Asset, Person, Transfer action
        assert len(graph["edges"]) == 2  # owns link + action edge
        node_ids = {n["id"] for n in graph["nodes"]}
        assert "Asset" in node_ids
        assert "action:Transfer" in node_ids


class TestAdminAPI:
    def test_list_ontologies(self, client):
        res = client.get("/api/ontologies")
        assert res.status_code == 200
        assert len(res.json()["ontologies"]) == 1

    def test_get_ontology(self, client):
        res = client.get("/api/ontologies/test_ont")
        assert res.status_code == 200
        assert res.json()["name"] == "test_ont"

    def test_get_graph(self, client):
        res = client.get("/api/ontologies/test_ont/graph")
        assert res.status_code == 200
        data = res.json()
        assert data["ontology"] == "test_ont"
        assert len(data["nodes"]) > 0

    def test_create_ontology(self, client, temp_dir):
        res = client.post("/api/ontologies", json={"name": "new_ont", "description": "new"})
        assert res.status_code == 200
        assert OntologyManager(temp_dir).load("new_ont").name == "new_ont"

    def test_update_ontology(self, client, temp_dir):
        ont = OntologyManager(temp_dir).load("test_ont")
        ont.description = "via API"
        res = client.put("/api/ontologies/test_ont", json=ont.model_dump())
        assert res.status_code == 200
        assert OntologyManager(temp_dir).load("test_ont").description == "via API"

    def test_add_object_type(self, client, temp_dir):
        res = client.post(
            "/api/ontologies/test_ont/object-types",
            json={
                "name": "Location",
                "display_name": "库位",
                "properties": [{"name": "id", "type": "string", "required": True}],
            },
        )
        assert res.status_code == 200
        ont = OntologyManager(temp_dir).load("test_ont")
        assert ont.get_object_type("Location") is not None

    def test_delete_link(self, client, temp_dir):
        res = client.delete("/api/ontologies/test_ont/links/owns")
        assert res.status_code == 200
        assert OntologyManager(temp_dir).load("test_ont").get_link("owns") is None

    def test_pages_load(self, client):
        assert client.get("/").status_code == 200
        assert client.get("/editor").status_code == 200
        assert client.get("/visualize").status_code == 200

class TestExamplesIntegration:
    def test_examples_loadable(self):
        app = create_app(EXAMPLES_DIR)
        client = TestClient(app)
        res = client.get("/api/ontologies")
        names = {o["name"] for o in res.json()["ontologies"]}
        assert "demo" in names
        assert "prototype" in names

    def test_prototype_graph(self):
        app = create_app(EXAMPLES_DIR)
        client = TestClient(app)
        res = client.get("/api/ontologies/prototype/graph")
        assert res.status_code == 200
        assert res.json()["stats"]["object_types"] == 4
