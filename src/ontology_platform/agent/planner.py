"""Planner implementations: rule-based and LLM-based."""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ontology_platform.agent.entities import extract_entities
from ontology_platform.ontology.service import OntologyService

IntentType = Literal["query", "action", "traverse", "clarify", "unknown"]


class PlanResult(BaseModel):
    intent: IntentType = "unknown"
    entities: dict[str, Any] = Field(default_factory=dict)
    plan: list[dict[str, Any]] = Field(default_factory=list)
    error: str = ""


class Planner(Protocol):
    def plan(self, message: str, service: OntologyService) -> PlanResult: ...


class RulePlanner:
    """Rule-based intent classification and tool plan generation."""

    def plan(self, message: str, service: OntologyService) -> PlanResult:
        text = message
        text_lower = text.lower()
        entities = extract_entities(text, service)
        intent = self._classify_intent(text_lower, entities)
        steps = self._build_plan(intent, entities, text, service)
        error = ""
        if intent == "action" and "action_name" not in entities:
            intent = "clarify"
            error = "Could not determine which action to execute"
            steps = [{"tool": "get_ontology_schema", "args": {}}]
        return PlanResult(intent=intent, entities=entities, plan=steps, error=error)

    def _classify_intent(self, text_lower: str, entities: dict[str, Any]) -> IntentType:
        action_keywords = [
            "执行", "操作", "预约", "领用", "归还", "报废",
            "execute", "action", "reserve", "checkout", "return",
        ]
        traverse_keywords = ["关联", "关系", "链接", "属于", "归属", "link", "related", "traverse"]
        query_keywords = ["查询", "搜索", "有哪些", "列出", "search", "query", "list", "find", "show"]

        if "action_name" in entities or any(kw in text_lower for kw in action_keywords):
            return "action"
        if "link_type" in entities or any(kw in text_lower for kw in traverse_keywords):
            return "traverse"
        if any(kw in text_lower for kw in query_keywords) or "object_type" in entities:
            return "query"
        if len(text_lower.strip()) < 3:
            return "clarify"
        return "query"

    def _build_plan(
        self,
        intent: IntentType,
        entities: dict[str, Any],
        text: str,
        service: OntologyService,
    ) -> list[dict[str, Any]]:
        if intent == "query":
            object_type = entities.get("object_type", service.ontology.object_types[0].name)
            if "object_id" in entities:
                return [
                    {
                        "tool": "get_object",
                        "args": {"object_type": object_type, "object_id": entities["object_id"]},
                    }
                ]
            return [
                {
                    "tool": "search_objects",
                    "args": {
                        "object_type": object_type,
                        "filters": entities.get("filters", {}),
                    },
                }
            ]

        if intent == "traverse":
            object_type = entities.get("object_type", service.ontology.object_types[0].name)
            link_type = entities.get("link_type")
            if not link_type and object_type == "Prototype" and any(
                kw in text for kw in ["项目", "归属", "属于"]
            ):
                link_type = "belongs_to"
            return [
                {
                    "tool": "traverse_links",
                    "args": {
                        "object_type": object_type,
                        "object_id": entities.get("object_id", ""),
                        "link_type": link_type,
                        "direction": "outgoing",
                    },
                }
            ]

        if intent == "action":
            return [
                {
                    "tool": "execute_action",
                    "args": {
                        "action_name": entities["action_name"],
                        "target_id": entities.get("object_id", ""),
                        "parameters": entities.get("action_params", {}),
                        "approved": False,
                    },
                }
            ]

        if intent == "clarify":
            return [{"tool": "get_ontology_schema", "args": {}}]

        return []


class LLMPlanner:
    """LLM-based planner using structured output, with rule-based fallback."""

    def __init__(self, model: BaseChatModel, fallback: RulePlanner | None = None) -> None:
        self.model = model
        self.fallback = fallback or RulePlanner()

    def plan(self, message: str, service: OntologyService) -> PlanResult:
        try:
            schema = service.get_schema_summary()
            system = (
                "You are an ontology agent planner. Given the ontology schema and user message, "
                "produce a JSON plan with fields: intent (query|action|traverse|clarify), "
                "entities (dict), plan (list of {tool, args}). "
                "Available tools: search_objects, get_object, traverse_links, execute_action, "
                "get_ontology_schema. Return ONLY valid JSON."
            )
            user = json.dumps(
                {"schema": schema, "message": message},
                ensure_ascii=False,
            )
            response = self.model.invoke([SystemMessage(content=system), HumanMessage(content=user)])
            content = response.content if isinstance(response.content, str) else str(response.content)
            parsed = self._parse_json(content)
            return PlanResult(
                intent=parsed.get("intent", "query"),
                entities=parsed.get("entities", {}),
                plan=parsed.get("plan", []),
            )
        except Exception:
            return self.fallback.plan(message, service)

    def _parse_json(self, content: str) -> dict[str, Any]:
        content = content.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
        if fence:
            content = fence.group(1).strip()
        return json.loads(content)


def create_planner(
    mode: str,
    service: OntologyService,
    model: BaseChatModel | None = None,
) -> Planner:
    rule = RulePlanner()
    if mode == "llm":
        if model is None:
            raise ValueError("LLM planner requires a chat model")
        return LLMPlanner(model, fallback=rule)
    if mode == "auto":
        if model is not None:
            return LLMPlanner(model, fallback=rule)
    return rule
