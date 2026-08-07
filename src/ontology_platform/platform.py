"""Main platform entry: wire ontology + LangGraph agent together."""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage

from ontology_platform.agent.graph import build_agent_graph
from ontology_platform.agent.state import AgentState
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.schema import ActionResult, OntologyObject
from ontology_platform.ontology.service import OntologyService


class AgentPlatform:
    """Ontology-based agent platform.

  Usage:
      platform = AgentPlatform.from_yaml("examples/demo_ontology.yaml")
      platform.seed_demo_data()
      response = platform.chat("查询所有 Person")
    """

    def __init__(self, registry: OntologyRegistry, ontology_name: str) -> None:
        self.registry = registry
        self.service = OntologyService(registry, ontology_name)
        self.graph = build_agent_graph(self.service)

    @classmethod
    def from_yaml(cls, path: str | Path) -> AgentPlatform:
        registry = OntologyRegistry.from_yaml(path)
        ontology_name = next(iter(registry.list_ontologies()))
        return cls(registry, ontology_name)

    @classmethod
    def from_registry(cls, registry: OntologyRegistry, ontology_name: str) -> AgentPlatform:
        return cls(registry, ontology_name)

    def register_action_handler(self, action_name: str, handler) -> None:
        self.registry.register_action_handler(self.service.ontology_name, action_name, handler)

    def chat(self, message: str, thread_id: str = "default") -> str:
        config = {"configurable": {"thread_id": thread_id}}
        initial_state: AgentState = {
            "messages": [HumanMessage(content=message)],
            "intent": "unknown",
            "entities": {},
            "plan": [],
            "ontology_results": [],
            "requires_approval": False,
            "approval_status": "",
            "final_response": "",
            "error": "",
        }
        result = self.graph.invoke(initial_state, config)
        return result.get("final_response", "")

    def get_service(self) -> OntologyService:
        return self.service

    def seed_demo_data(self) -> None:
        """Seed minimal demo data if the ontology has Person/Project types."""
        ontology = self.service.ontology
        if ontology.get_object_type("Person"):
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
        if ontology.get_object_type("Project"):
            self.service.create_object(
                "Project",
                {"id": "PRJ-001", "name": "Alpha 项目", "status": "active"},
                object_id="PRJ-001",
            )

        if (
            ontology.get_object_type("Person")
            and ontology.get_object_type("Project")
            and ontology.get_link("works_on")
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
