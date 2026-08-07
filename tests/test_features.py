"""Tests for persistence, approval flow, and LLM planner."""

import json
import tempfile
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from ontology_platform.agent.config import AgentConfig
from ontology_platform.agent.planner import LLMPlanner, RulePlanner
from ontology_platform.apps.prototype import PrototypeApp
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.service import OntologyService
from ontology_platform.ontology.store import SQLiteStore
from ontology_platform.platform import AgentPlatform

PROTOTYPE_ONTOLOGY = Path(__file__).parent.parent / "examples" / "prototype_ontology.yaml"
DEMO_ONTOLOGY = Path(__file__).parent.parent / "examples" / "demo_ontology.yaml"


class TestSQLiteStore:
    def test_persist_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            registry = OntologyRegistry.from_yaml(DEMO_ONTOLOGY)

            svc1 = OntologyService(registry, "demo", store=SQLiteStore(db_path))
            svc1.create_object("Person", {"id": "P-99", "name": "持久化测试", "department": "QA"})

            svc2 = OntologyService(registry, "demo", store=SQLiteStore(db_path))
            obj = svc2.get_object("Person", "P-99")
            assert obj is not None
            assert obj.properties["name"] == "持久化测试"

    def test_platform_with_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "platform.db"
            config = AgentConfig(store_path=str(db_path))
            platform = AgentPlatform.from_yaml(DEMO_ONTOLOGY, config=config)
            platform.seed_demo_data()

            platform2 = AgentPlatform.from_yaml(DEMO_ONTOLOGY, config=config)
            assert platform2.get_service().get_object("Person", "P-001") is not None


class TestApprovalFlow:
    @pytest.fixture
    def app(self) -> PrototypeApp:
        config = AgentConfig(enable_approval_flow=True, thread_id="approval-test")
        app = PrototypeApp.create(PROTOTYPE_ONTOLOGY, config=config)
        app.seed()
        return app

    def test_interrupt_on_action(self, app: PrototypeApp):
        result = app.chat_raw("预约 SN-2024-003", thread_id="t1")
        assert result.interrupted is True
        assert "审批" in result.response
        assert result.pending_action.get("args", {}).get("action_name") == "ReservePrototype"

    def test_resume_reject(self, app: PrototypeApp):
        app.chat_raw("预约 SN-2024-003", thread_id="t2")
        result = app.platform.resume(approved=False, thread_id="t2")
        assert result.interrupted is False
        assert "拒绝" in result.response
        proto = app.service.get_object("Prototype", "SN-2024-003")
        assert proto.properties["status"] == "available"

    def test_resume_approve(self, app: PrototypeApp):
        app.chat_raw("预约 SN-2024-001", thread_id="t3")
        result = app.platform.resume(approved=True, thread_id="t3", roles=["admin"])
        assert result.interrupted is False
        # Missing person_id params — action fails but flow completes
        assert "person_id" in result.response or "缺少" in result.response

    def test_no_approval_when_disabled(self):
        config = AgentConfig(enable_approval_flow=False)
        app = PrototypeApp.create(PROTOTYPE_ONTOLOGY, config=config)
        app.seed()
        result = app.chat_raw("预约 SN-2024-003")
        assert result.interrupted is False
        assert "审批" in result.response


class TestLLMPlanner:
    def test_llm_planner_produces_plan(self):
        plan_json = json.dumps(
            {
                "intent": "query",
                "entities": {"object_type": "Person"},
                "plan": [
                    {"tool": "search_objects", "args": {"object_type": "Person", "filters": {}}}
                ],
            },
            ensure_ascii=False,
        )
        model = GenericFakeChatModel(messages=iter([AIMessage(content=plan_json)]))
        registry = OntologyRegistry.from_yaml(DEMO_ONTOLOGY)
        service = OntologyService(registry, "demo")
        planner = LLMPlanner(model)

        result = planner.plan("帮我查一下所有人员", service)
        assert result.intent == "query"
        assert len(result.plan) == 1
        assert result.plan[0]["tool"] == "search_objects"

    def test_llm_planner_fallback_on_error(self):
        model = GenericFakeChatModel(messages=iter([AIMessage(content="not valid json")]))
        registry = OntologyRegistry.from_yaml(DEMO_ONTOLOGY)
        service = OntologyService(registry, "demo")
        planner = LLMPlanner(model)

        result = planner.plan("查询所有 Person", service)
        assert result.intent == "query"

    def test_platform_with_llm_planner(self):
        plan_json = json.dumps(
            {
                "intent": "query",
                "entities": {"object_type": "Person"},
                "plan": [
                    {"tool": "search_objects", "args": {"object_type": "Person", "filters": {}}}
                ],
            }
        )
        model = GenericFakeChatModel(messages=iter([AIMessage(content=plan_json)]))
        config = AgentConfig(planner_mode="llm", enable_approval_flow=False)
        platform = AgentPlatform.from_yaml(DEMO_ONTOLOGY, config=config, model=model)
        platform.seed_demo_data()
        response = platform.chat("find all people").response
        assert "张三" in response or "找到" in response

class TestRulePlanner:
    def test_rule_planner_still_works(self):
        registry = OntologyRegistry.from_yaml(DEMO_ONTOLOGY)
        service = OntologyService(registry, "demo")
        planner = RulePlanner()
        result = planner.plan("查询所有 Person", service)
        assert result.intent == "query"
        assert result.plan[0]["tool"] == "search_objects"
