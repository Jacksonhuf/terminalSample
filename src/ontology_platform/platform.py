"""Main platform entry: wire ontology + LangGraph agent together."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from ontology_platform.agent.config import AgentConfig
from ontology_platform.agent.graph import build_agent_graph
from ontology_platform.agent.planner import create_planner
from ontology_platform.agent.state import AgentState
from ontology_platform.governance.audit import AuditLogger
from ontology_platform.governance.context import ExecutionContext
from ontology_platform.governance.policy import PolicyEngine
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.schema import ActionResult, OntologyObject
from ontology_platform.ontology.service import OntologyService
from ontology_platform.ontology.store import MemoryStore, SQLiteStore


@dataclass
class ChatResult:
    """Result of a chat or resume interaction."""

    response: str
    interrupted: bool = False
    thread_id: str = "default"
    pending_action: dict[str, Any] = field(default_factory=dict)
    intent: str = ""
    plan: list[dict[str, Any]] = field(default_factory=list)
    ontology_results: list[dict[str, Any]] = field(default_factory=list)


class AgentPlatform:
    """Ontology-based agent platform."""

    def __init__(
        self,
        registry: OntologyRegistry,
        ontology_name: str,
        config: AgentConfig | None = None,
        model: BaseChatModel | None = None,
    ) -> None:
        self.registry = registry
        self.config = config or AgentConfig()
        self._model = model
        store = self._create_store()
        audit = AuditLogger(self.config.get_audit_path()) if self.config.enable_governance else None
        self.service = OntologyService(
            registry,
            ontology_name,
            store=store,
            policy=PolicyEngine(),
            audit=audit,
        )
        planner = create_planner(self.config.planner_mode, self.service, model)
        self.graph = build_agent_graph(self.service, planner, self.config)

    def _create_store(self) -> MemoryStore | SQLiteStore:
        if self.config.store_path:
            return SQLiteStore(self.config.store_path)
        return MemoryStore()

    @classmethod
    def from_yaml(
        cls,
        path: str | Path,
        config: AgentConfig | None = None,
        model: BaseChatModel | None = None,
    ) -> AgentPlatform:
        registry = OntologyRegistry.from_yaml(path)
        ontology_name = next(iter(registry.list_ontologies()))
        return cls(registry, ontology_name, config, model)

    def register_action_handler(self, action_name: str, handler) -> None:
        self.registry.register_action_handler(self.service.ontology_name, action_name, handler)

    def _build_config(self, thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def _initial_state(self, message: str) -> AgentState:
        return {
            "messages": [HumanMessage(content=message)],
            "intent": "unknown",
            "entities": {},
            "plan": [],
            "ontology_results": [],
            "requires_approval": False,
            "approval_status": "",
            "pending_action": {},
            "interrupted": False,
            "final_response": "",
            "error": "",
        }

    def _build_chat_result(
        self,
        result: dict,
        snapshot,
        thread_id: str,
        *,
        interrupted: bool | None = None,
    ) -> ChatResult:
        is_interrupted = interrupted if interrupted is not None else bool(snapshot.next)
        values = snapshot.values or result
        pending = values.get("pending_action", {}) or result.get("pending_action", {})

        if is_interrupted:
            action = pending.get("args", {}).get("action_name", "操作")
            target = pending.get("args", {}).get("target_id", "")
            response = (
                f"⏸️ 操作「{action}」(目标: {target}) 需要审批。\n"
                f"请批准或拒绝该操作。"
            )
        else:
            response = result.get("final_response", "")

        return ChatResult(
            response=response,
            interrupted=is_interrupted,
            thread_id=thread_id,
            pending_action=pending,
            intent=values.get("intent", result.get("intent", "")),
            plan=values.get("plan", result.get("plan", [])),
            ontology_results=values.get("ontology_results", result.get("ontology_results", [])),
        )

    def _set_context(self, thread_id: str, user_id: str | None = None, roles: list[str] | None = None) -> ExecutionContext:
        ctx = ExecutionContext(
            user_id=user_id or self.config.user_id,
            roles=roles or list(self.config.roles),
            thread_id=thread_id,
        )
        self.service.set_execution_context(ctx)
        return ctx

    def chat(
        self,
        message: str,
        thread_id: str | None = None,
        user_id: str | None = None,
        roles: list[str] | None = None,
    ) -> ChatResult:
        tid = thread_id or self.config.thread_id
        self._set_context(tid, user_id, roles)
        config = self._build_config(tid)
        result = self.graph.invoke(self._initial_state(message), config)
        snapshot = self.graph.get_state(config)
        return self._build_chat_result(result, snapshot, tid)

    def resume(
        self,
        approved: bool = True,
        thread_id: str | None = None,
        user_id: str | None = None,
        roles: list[str] | None = None,
    ) -> ChatResult:
        """Resume an interrupted approval flow."""
        tid = thread_id or self.config.thread_id
        self._set_context(tid, user_id, roles)
        config = self._build_config(tid)
        result = self.graph.invoke(Command(resume=approved), config)
        snapshot = self.graph.get_state(config)
        return self._build_chat_result(result, snapshot, tid)

    def get_service(self) -> OntologyService:
        return self.service

    def get_audit_logs(self, action_name: str | None = None, user_id: str | None = None, limit: int = 100):
        if self.service.audit is None:
            return []
        return self.service.audit.query(action_name=action_name, user_id=user_id, limit=limit)

    def seed_demo_data(self) -> None:
        """Seed minimal demo data if the ontology has Person/Project types."""
        ontology = self.service.ontology
        if ontology.get_object_type("Person") and not self.service.get_object("Person", "P-001"):
            self.service.create_object(
                "Person",
                {"id": "P-001", "name": "张三", "department": "研发部"},
                object_id="P-001",
            )
            self.service.create_object(
                "Person",
                {"id": "P-002", "name": "李四", "department": "测试部"},
                object_id="P-002",
            )
        if ontology.get_object_type("Project") and not self.service.get_object("Project", "PRJ-001"):
            self.service.create_object(
                "Project",
                {"id": "PRJ-001", "name": "Alpha 项目", "status": "active"},
                object_id="PRJ-001",
            )

        if (
            ontology.get_object_type("Person")
            and ontology.get_object_type("Project")
            and ontology.get_link("works_on")
            and not self.service.store.get_links(source_type="Person", source_id="P-001")
        ):
            self.service.create_link("works_on", "Person", "P-001", "Project", "PRJ-001")

        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        ontology = self.service.ontology

        if ontology.get_action("AssignToProject"):

            def assign_handler(svc: OntologyService, target: OntologyObject, params: dict) -> ActionResult:
                project_id = params.get("project_id")
                if not project_id:
                    return ActionResult(success=False, message="缺少 project_id 参数")
                project = svc.get_object("Project", project_id)
                if project is None:
                    return ActionResult(success=False, message=f"项目不存在: {project_id}")
                svc.create_link("works_on", "Person", target.object_id, "Project", project_id)
                return ActionResult(
                    success=True,
                    message=f"已将 {target.properties.get('name', target.object_id)} 分配到项目 {project.properties.get('name', project_id)}",
                    data={"person_id": target.object_id, "project_id": project_id},
                )

            self.register_action_handler("AssignToProject", assign_handler)
