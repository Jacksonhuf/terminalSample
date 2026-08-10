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

    def test_delete_ontology(self, client, temp_dir):
        res = client.delete("/api/ontologies/test_ont")
        assert res.status_code == 200
        assert res.json()["name"] == "test_ont"
        with pytest.raises(FileNotFoundError):
            OntologyManager(temp_dir).load("test_ont")

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
        assert client.get("/admin/ontologies").status_code == 200
        editor = client.get("/editor", follow_redirects=False)
        assert editor.status_code in (200, 302)
        if editor.status_code == 302:
            assert editor.headers["location"] == "/admin/ontologies/edit"
        else:
            assert "shell.js" in editor.text
        visualize = client.get("/visualize", follow_redirects=False)
        assert visualize.status_code in (200, 302)
        assert client.get("/admin/operations/overview").status_code == 200
        assert client.get("/admin/apps/prototype/dashboard").status_code == 200
        operations = client.get("/operations", follow_redirects=False)
        assert operations.status_code in (200, 302)


class TestOperationsAPI:
    def test_operations_status_unconfigured(self, client):
        res = client.get("/api/operations/status")
        assert res.status_code == 200
        data = res.json()
        assert data["audit_configured"] is False
        assert data["integrations_configured"] is False

    def test_audit_logs_unconfigured(self, client):
        res = client.get("/api/audit-logs")
        assert res.status_code == 200
        assert res.json()["configured"] is False

    def test_message_logs_and_outreach(self, temp_dir, sample_ontology):
        from datetime import datetime, timezone

        from ontology_platform.integrations.message_log import MessageLogStore
        from ontology_platform.integrations.outreach.store import OutreachStore
        from ontology_platform.integrations.schema import ChannelType

        db_path = temp_dir / "ops.db"
        mgr = OntologyManager(temp_dir)
        mgr.save(sample_ontology)
        app = create_app(temp_dir, audit_path=db_path, integrations_db_path=db_path)
        client = TestClient(app)

        MessageLogStore(db_path).append(
            channel="chat",
            template_id="notify_custodian",
            recipients=["zhangsan"],
            subject="test",
            body="hello",
            status="sent",
            object_type="Prototype",
            object_id="SN-001",
        )
        OutreachStore(db_path).create_task(
            channel=ChannelType.EMAIL,
            template_id="reminder",
            recipients=["P-001"],
            due_at=datetime.now(timezone.utc).isoformat(),
            object_type="Prototype",
            object_id="SN-001",
        )

        msg_res = client.get("/api/message-logs")
        assert msg_res.status_code == 200
        assert msg_res.json()["count"] == 1

        task_res = client.get("/api/outreach-tasks?status=pending")
        assert task_res.status_code == 200
        assert task_res.json()["count"] == 1

        status_res = client.get("/api/operations/status")
        assert status_res.json()["integrations_configured"] is True


class TestApprovalsAPI:
    def test_approvals_unconfigured(self, client):
        res = client.get("/api/approvals")
        assert res.status_code == 200
        assert res.json()["configured"] is False

    def test_approvals_list(self, temp_dir, sample_ontology):
        from ontology_platform.governance.approval_store import ApprovalStore

        db_path = temp_dir / "ops.db"
        mgr = OntologyManager(temp_dir)
        mgr.save(sample_ontology)
        app = create_app(temp_dir, store_path=db_path)
        client = TestClient(app)

        ApprovalStore(db_path).create_pending(
            thread_id="t-1",
            action_name="ReservePrototype",
            target_id="SN-001",
            requester_id="alice",
        )
        res = client.get("/api/approvals?status=pending")
        assert res.status_code == 200
        assert res.json()["count"] == 1


class TestPrototypeDashboardAPI:
    def test_dashboard_unconfigured(self, client):
        res = client.get("/api/prototype/dashboard")
        assert res.status_code == 200
        assert res.json()["configured"] is False

    def test_dashboard_with_seed(self, temp_dir):
        db_path = temp_dir / "ops.db"
        app = create_app(
            EXAMPLES_DIR,
            store_path=db_path,
            ontology_yaml_path=EXAMPLES_DIR / "prototype_ontology.yaml",
            ontology_db_path=temp_dir / "prototype.db",
        )
        client = TestClient(app)

        seed_res = client.post("/api/prototype/seed")
        assert seed_res.status_code == 200
        assert seed_res.json()["seeded"] is True

        dash_res = client.get("/api/prototype/dashboard")
        assert dash_res.status_code == 200
        data = dash_res.json()
        assert data["configured"] is True
        assert data["summary"]["prototype_total"] == 4
        assert data["by_status"]["available"] == 2

        seed_again = client.post("/api/prototype/seed")
        assert seed_again.json()["seeded"] is False


class TestBatchApprovalAPI:
    def test_batch_resolve_empty(self, temp_dir, sample_ontology):
        db_path = temp_dir / "ops.db"
        mgr = OntologyManager(temp_dir)
        mgr.save(sample_ontology)
        app = create_app(temp_dir, store_path=db_path)
        client = TestClient(app)

        res = client.post("/api/approvals/batch-resolve", json={"request_ids": []})
        assert res.status_code == 400

    def test_batch_resolve_updates_records(self, temp_dir, sample_ontology):
        from ontology_platform.governance.approval_store import ApprovalStore

        db_path = temp_dir / "ops.db"
        mgr = OntologyManager(temp_dir)
        mgr.save(sample_ontology)
        app = create_app(
            temp_dir,
            store_path=db_path,
            ontology_yaml_path=EXAMPLES_DIR / "prototype_ontology.yaml",
        )
        client = TestClient(app)
        store = ApprovalStore(db_path)
        r1 = store.create_pending(thread_id="t-1", action_name="ReservePrototype", target_id="SN-001")
        r2 = store.create_pending(thread_id="t-2", action_name="CheckoutPrototype", target_id="SN-002")

        res = client.post(
            "/api/approvals/batch-resolve",
            json={
                "request_ids": [r1.id, r2.id],
                "approved": True,
                "resolver_id": "admin-ui",
                "resolver_roles": ["admin"],
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 2
        assert len(body["succeeded"]) == 2
        assert body["failed"] == []

        for rid in (r1.id, r2.id):
            item = store.get(rid)
            assert item is not None
            assert item.status == "approved"


class TestConnectorsAPI:
    def test_list_connectors(self):
        app = create_app(EXAMPLES_DIR)
        client = TestClient(app)
        res = client.get("/api/connectors")
        assert res.status_code == 200
        assert res.json()["count"] >= 1

    def test_credentials_unconfigured(self, client):
        res = client.get("/api/credentials")
        assert res.status_code == 200
        assert res.json()["configured"] is False

    def test_credentials_crud(self, temp_dir):
        db_path = temp_dir / "ops.db"
        app = create_app(EXAMPLES_DIR, store_path=db_path)
        client = TestClient(app)

        create_res = client.post(
            "/api/credentials",
            json={
                "name": "ERP",
                "username": "ops",
                "password": "secret",
                "credential_id": "cred-test",
                "login_url": "https://erp.example.com/login",
            },
        )
        assert create_res.status_code == 200
        assert create_res.json()["password_set"] is True
        assert "password" not in create_res.json()

        list_res = client.get("/api/credentials")
        assert list_res.json()["count"] == 1

        rotate_res = client.put(
            "/api/credentials/cred-test/password",
            json={"password": "new-secret"},
        )
        assert rotate_res.status_code == 200

        delete_res = client.delete("/api/credentials/cred-test")
        assert delete_res.status_code == 200

    def test_connector_task_api(self, temp_dir):
        import shutil

        connectors_dir = temp_dir / "connectors"
        shutil.copytree(EXAMPLES_DIR / "connectors", connectors_dir)
        db_path = temp_dir / "ops.db"
        app = create_app(EXAMPLES_DIR, store_path=db_path, connectors_dir=connectors_dir)
        client = TestClient(app)
        client.post(
            "/api/credentials",
            json={
                "name": "ERP",
                "username": "ops",
                "password": "secret",
                "credential_id": "cred-task",
            },
        )
        connector = client.get("/api/connectors/prototype_erp").json()
        connector["credential_ref"] = "cred-task"
        client.put("/api/connectors/prototype_erp", json=connector)

        task_res = client.post("/api/connectors/prototype_erp/task")
        assert task_res.status_code == 200
        task = task_res.json()
        assert task["login"]["username"] == "ops"
        assert task["login"]["password_provided"] is True
        assert task["login"].get("password") is None


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
        assert res.json()["stats"]["object_types"] == 5
