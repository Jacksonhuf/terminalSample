"""Tests for ontology agent platform."""

import json
from pathlib import Path

import pytest

from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.schema import ActionResult, OntologyDef
from ontology_platform.ontology.service import OntologyService
from ontology_platform.platform import AgentPlatform

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
DEMO_ONTOLOGY = EXAMPLES_DIR / "demo_ontology.yaml"


@pytest.fixture
def platform() -> AgentPlatform:
    p = AgentPlatform.from_yaml(DEMO_ONTOLOGY)
    p.seed_demo_data()
    return p


@pytest.fixture
def service(platform: AgentPlatform) -> OntologyService:
    return platform.get_service()


class TestOntologySchema:
    def test_load_yaml(self):
        registry = OntologyRegistry.from_yaml(DEMO_ONTOLOGY)
        ontology = registry.get("demo")
        assert ontology is not None
        assert len(ontology.object_types) == 2
        assert len(ontology.links) == 1
        assert len(ontology.actions) == 1


class TestOntologyService:
    def test_create_and_search_objects(self, service: OntologyService):
        obj = service.create_object("Person", {"id": "P-100", "name": "王五", "department": "产品部"})
        assert obj.object_id == "P-100"

        results = service.search_objects("Person", {"department": "产品部"})
        assert len(results) == 1
        assert results[0].properties["name"] == "王五"

    def test_create_link(self, service: OntologyService):
        links = service.traverse_links("Person", "P-001", "works_on")
        assert len(links) == 1
        assert links[0]["object"]["object_type"] == "Project"

    def test_action_requires_approval(self, service: OntologyService, platform: AgentPlatform):
        def handler(svc, target, params):
            return ActionResult(success=True, message="ok")

        platform.register_action_handler("AssignToProject", handler)
        result = service.execute_action("AssignToProject", "P-001", {"project_id": "PRJ-001"})
        assert result.success is False
        assert result.requires_approval is True

    def test_action_with_approval(self, service: OntologyService):
        result = service.execute_action(
            "AssignToProject", "P-002", {"project_id": "PRJ-001"}, approved=True
        )
        assert result.success is True

    def test_schema_summary(self, service: OntologyService):
        summary = service.get_schema_summary()
        assert summary["name"] == "demo"
        assert len(summary["object_types"]) == 2


class TestAgentPlatform:
    def test_chat_query(self, platform: AgentPlatform):
        response = platform.chat("查询所有 Person")
        assert "张三" in response or "找到" in response

    def test_chat_traverse(self, platform: AgentPlatform):
        response = platform.chat("查询 P-001 的关联")
        assert "Project" in response or "关联" in response

    def test_chat_clarify(self, platform: AgentPlatform):
        response = platform.chat("?")
        assert "Ontology" in response or "本体" in response

    def test_tools_creation(self, platform: AgentPlatform):
        from ontology_platform.agent.tools import create_ontology_tools

        tools = create_ontology_tools(platform.get_service())
        assert len(tools) == 5
        search_tool = next(t for t in tools if t.name == "search_objects")
        output = search_tool.invoke({"object_type": "Person", "filters": {}})
        data = json.loads(output)
        assert len(data) >= 2
