"""Tests for prototype management app."""

from pathlib import Path

import pytest

from ontology_platform.apps.prototype import PrototypeApp
from ontology_platform.governance.context import ExecutionContext

PROTOTYPE_ONTOLOGY = Path(__file__).parent.parent / "examples" / "prototype_ontology.yaml"


@pytest.fixture
def app() -> PrototypeApp:
    prototype_app = PrototypeApp.create(PROTOTYPE_ONTOLOGY)
    prototype_app.seed()
    return prototype_app


class TestPrototypeOntology:
    def test_load_schema(self, app: PrototypeApp):
        schema = app.service.get_schema_summary()
        assert schema["name"] == "prototype"
        type_names = {t["name"] for t in schema["object_types"]}
        assert "Prototype" in type_names
        assert len(schema["actions"]) == 4

    def test_seed_data(self, app: PrototypeApp):
        prototypes = app.service.search_objects("Prototype")
        assert len(prototypes) == 4
        available = app.list_available()
        assert len(available) == 2

    def test_links(self, app: PrototypeApp):
        links = app.service.traverse_links("Prototype", "SN-2024-001", "belongs_to")
        assert len(links) == 1
        assert links[0]["object"]["object_type"] == "Project"

    def test_reserve_requires_approval(self, app: PrototypeApp):
        result = app.service.execute_action(
            "ReservePrototype",
            "SN-2024-001",
            {"person_id": "P-002", "start_date": "2026-08-10", "end_date": "2026-08-12"},
        )
        assert result.requires_approval is True

    def test_reserve_approved(self, app: PrototypeApp):
        app.service.set_execution_context(ExecutionContext(user_id="admin1", roles=["admin"]))
        result = app.service.execute_action(
            "ReservePrototype",
            "SN-2024-001",
            {"person_id": "P-002", "start_date": "2026-08-10", "end_date": "2026-08-12"},
            approved=True,
        )
        assert result.success is True
        proto = app.service.get_object("Prototype", "SN-2024-001")
        assert proto.properties["status"] == "reserved"

    def test_checkout_and_return(self, app: PrototypeApp):
        app.service.set_execution_context(ExecutionContext(user_id="admin1", roles=["admin"]))
        checkout = app.service.execute_action(
            "CheckoutPrototype",
            "SN-2024-003",
            {"person_id": "P-002"},
            approved=True,
        )
        assert checkout.success is True

        proto = app.service.get_object("Prototype", "SN-2024-003")
        assert proto.properties["status"] == "in_use"

        returned = app.service.execute_action(
            "ReturnPrototype",
            "SN-2024-003",
            {"condition": "good"},
        )
        assert returned.success is True
        proto = app.service.get_object("Prototype", "SN-2024-003")
        assert proto.properties["status"] == "available"

    def test_retire(self, app: PrototypeApp):
        app.service.set_execution_context(ExecutionContext(user_id="admin1", roles=["admin"]))
        result = app.service.execute_action(
            "RetirePrototype",
            "SN-2024-004",
            {"reason": "硬件损坏"},
            approved=True,
        )
        assert result.success is True
        proto = app.service.get_object("Prototype", "SN-2024-004")
        assert proto.properties["status"] == "retired"


class TestPrototypeAgent:
    def test_query_available(self, app: PrototypeApp):
        response = app.chat("查询所有可用样机")
        assert "SN-2024" in response

    def test_query_by_model(self, app: PrototypeApp):
        response = app.chat("查询 X100 型号样机")
        assert "X100" in response

    def test_query_single(self, app: PrototypeApp):
        response = app.chat("查询 SN-2024-001")
        assert "SN-2024-001" in response

    def test_traverse(self, app: PrototypeApp):
        response = app.chat("SN-2024-001 归属哪个项目")
        assert "Project" in response or "Alpha" in response or "关联" in response

    def test_action_approval_hint(self, app: PrototypeApp):
        response = app.chat("预约 SN-2024-003")
        assert "审批" in response
