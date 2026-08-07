"""LangGraph node implementations for the ontology agent."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from ontology_platform.agent.state import AgentState
from ontology_platform.ontology.service import OntologyService


def _last_user_message(state: AgentState) -> str:
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return ""


def _extract_filters(text: str) -> dict[str, Any]:
    """Extract property filters from natural language."""
    filters: dict[str, Any] = {}
    text_lower = text.lower()
    if any(kw in text_lower for kw in ["可用", "available", "空闲"]):
        filters["status"] = "available"
    elif any(kw in text_lower for kw in ["使用中", "in_use", "在用"]):
        filters["status"] = "in_use"
    elif any(kw in text_lower for kw in ["维修", "maintenance"]):
        filters["status"] = "maintenance"
    elif any(kw in text_lower for kw in ["报废", "retired"]):
        filters["status"] = "retired"
    # 型号过滤 e.g. X100
    model_match = re.search(r"\b(X\d{3})\b", text, re.IGNORECASE)
    if model_match:
        filters["model"] = model_match.group(1).upper()
    return filters


def _extract_entities(text: str, service: OntologyService) -> dict[str, Any]:
    """Rule-based entity extraction for the minimal platform."""
    entities: dict[str, Any] = {}
    text_lower = text.lower()
    entities["filters"] = _extract_filters(text)

    for obj_type in service.ontology.object_types:
        names = [obj_type.name.lower(), obj_type.display_name.lower()]
        if any(n and n in text_lower for n in names):
            entities["object_type"] = obj_type.name

    # 样机领域常用中文别名
    type_aliases = {
        "样机": "Prototype",
        "原型机": "Prototype",
        "设备": "Prototype",
    }
    for alias, type_name in type_aliases.items():
        if alias in text and service.ontology.get_object_type(type_name):
            entities["object_type"] = type_name

    id_match = re.search(
        r"\b(SN-\d{4}-\d{3}|[A-Z]{2,}-\d{4}-\d{3,}|\w+-\d+)\b",
        text,
        re.IGNORECASE,
    )
    if id_match:
        entities["object_id"] = id_match.group(1).upper()
        if entities["object_id"].startswith("SN-") and service.ontology.get_object_type("Prototype"):
            entities["object_type"] = "Prototype"

    for action in service.ontology.actions:
        keywords = [
            action.name.lower(),
            action.display_name.lower(),
            *[k.lower() for k in action.keywords],
        ]
        if any(kw and kw in text_lower for kw in keywords):
            entities["action_name"] = action.name

    for link in service.ontology.links:
        if link.name.lower() in text_lower:
            entities["link_type"] = link.name

    return entities


def make_router_node(service: OntologyService):
    """Classify user intent without requiring an LLM."""

    def router(state: AgentState) -> dict[str, Any]:
        text = _last_user_message(state).lower()
        entities = _extract_entities(_last_user_message(state), service)

        action_keywords = [
            "执行", "操作", "预约", "领用", "归还", "报废",
            "创建", "删除", "更新", "execute", "action", "reserve", "checkout", "return",
        ]
        traverse_keywords = ["关联", "关系", "链接", "属于", "归属", "link", "related", "traverse"]
        query_keywords = ["查询", "搜索", "有哪些", "列出", "search", "query", "list", "find", "show"]

        if "action_name" in entities or any(kw in text for kw in action_keywords):
            intent = "action"
        elif "link_type" in entities or any(kw in text for kw in traverse_keywords):
            intent = "traverse"
        elif any(kw in text for kw in query_keywords) or "object_type" in entities:
            intent = "query"
        elif len(text.strip()) < 3:
            intent = "clarify"
        else:
            intent = "query"

        return {"intent": intent, "entities": entities, "error": ""}

    return router


def make_planner_node(service: OntologyService):
    """Build an execution plan from intent and entities."""

    def planner(state: AgentState) -> dict[str, Any]:
        intent = state["intent"]
        entities = state.get("entities", {})
        plan: list[dict[str, Any]] = []

        if intent == "query":
            filters = entities.get("filters", {})
            object_type = entities.get("object_type", service.ontology.object_types[0].name)
            if "object_id" in entities:
                plan = [
                    {
                        "tool": "get_object",
                        "args": {
                            "object_type": object_type,
                            "object_id": entities["object_id"],
                        },
                    }
                ]
            else:
                plan.append(
                    {
                        "tool": "search_objects",
                        "args": {
                            "object_type": object_type,
                            "filters": filters,
                        },
                    }
                )

        elif intent == "traverse":
            object_type = entities.get("object_type", service.ontology.object_types[0].name)
            link_type = entities.get("link_type")
            if not link_type and object_type == "Prototype" and any(
                kw in _last_user_message(state) for kw in ["项目", "归属", "属于"]
            ):
                link_type = "belongs_to"
            plan.append(
                {
                    "tool": "traverse_links",
                    "args": {
                        "object_type": object_type,
                        "object_id": entities.get("object_id", ""),
                        "link_type": link_type,
                        "direction": "outgoing",
                    },
                }
            )

        elif intent == "action":
            if "action_name" not in entities:
                return {
                    "plan": [],
                    "intent": "clarify",
                    "error": "Could not determine which action to execute",
                }
            plan.append(
                {
                    "tool": "execute_action",
                    "args": {
                        "action_name": entities["action_name"],
                        "target_id": entities.get("object_id", ""),
                        "parameters": {},
                        "approved": False,
                    },
                }
            )

        elif intent == "clarify":
            plan.append({"tool": "get_ontology_schema", "args": {}})

        return {"plan": plan}

    return planner


def make_executor_node(tools_by_name: dict[str, Any]):
    """Execute the planned tool calls."""

    def executor(state: AgentState) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        requires_approval = False

        for step in state.get("plan", []):
            tool_name = step["tool"]
            tool = tools_by_name.get(tool_name)
            if tool is None:
                results.append({"tool": tool_name, "error": "Tool not found"})
                continue

            try:
                output = tool.invoke(step.get("args", {}))
                parsed = json.loads(output) if isinstance(output, str) else output

                if isinstance(parsed, dict) and parsed.get("requires_approval"):
                    requires_approval = True

                results.append({"tool": tool_name, "result": parsed})
            except Exception as exc:
                results.append({"tool": tool_name, "error": str(exc)})

        return {"ontology_results": results, "requires_approval": requires_approval}

    return executor


def make_response_node(service: OntologyService):
    """Synthesize a natural language response from ontology results."""

    def respond(state: AgentState) -> dict[str, Any]:
        if state.get("error"):
            response = f"抱歉，无法处理您的请求：{state['error']}"
        elif state.get("intent") == "clarify":
            schema = service.get_schema_summary()
            types = ", ".join(t["name"] for t in schema["object_types"])
            actions = ", ".join(a["name"] for a in schema["actions"])
            response = (
                f"我是基于 Ontology 的智能体。当前本体「{schema['name']}」支持：\n"
                f"- 对象类型: {types}\n"
                f"- 可执行动作: {actions}\n"
                f"您可以查询对象、遍历关系或执行动作。"
            )
        elif state.get("requires_approval"):
            response = "该操作需要审批后才能执行。请确认后重新提交（approved=true）。"
        elif not state.get("ontology_results"):
            response = "未找到相关结果。"
        else:
            response = _format_results(state)

        return {
            "final_response": response,
            "messages": [AIMessage(content=response)],
        }

    return respond


def _format_results(state: AgentState) -> str:
    lines = []
    for item in state.get("ontology_results", []):
        if "error" in item:
            lines.append(f"❌ {item['tool']}: {item['error']}")
            continue

        result = item.get("result")
        tool = item["tool"]

        if tool == "search_objects" and isinstance(result, list):
            if not result:
                lines.append("未找到匹配的对象。")
            else:
                lines.append(f"找到 {len(result)} 个对象：")
                for obj in result[:10]:
                    props = obj.get("properties", {})
                    label = props.get("serial_number") or props.get("name") or props.get("id", obj.get("object_id", "?"))
                    status = props.get("status", "")
                    model = props.get("model", "")
                    extra_parts = [p for p in [f"model={model}" if model else "", f"status={status}" if status else ""] if p]
                    extra = f", {', '.join(extra_parts)}" if extra_parts else ""
                    lines.append(f"  - [{obj['object_type']}] {label} (id={obj['object_id']}{extra})")

        elif tool == "get_object" and isinstance(result, dict):
            if "error" in result:
                lines.append(f"对象未找到。")
            else:
                props = result.get("properties", {})
                lines.append(f"对象 [{result['object_type']}] {result['object_id']}:")
                for k, v in props.items():
                    lines.append(f"  {k}: {v}")

        elif tool == "traverse_links" and isinstance(result, list):
            if not result:
                lines.append("未找到关联对象。")
            else:
                lines.append(f"找到 {len(result)} 个关联：")
                for link in result[:10]:
                    obj = link.get("object", {})
                    props = obj.get("properties", {})
                    name = props.get("name", obj.get("object_id", "?"))
                    lines.append(
                        f"  - [{link['link_type']}] {obj.get('object_type')}/{name}"
                    )

        elif tool == "execute_action" and isinstance(result, dict):
            if result.get("success"):
                lines.append(f"✅ {result.get('message', '操作成功')}")
            else:
                lines.append(f"❌ {result.get('message', '操作失败')}")

        elif tool == "get_ontology_schema":
            lines.append("已加载本体 Schema。")

        else:
            lines.append(json.dumps(result, ensure_ascii=False, indent=2))

    return "\n".join(lines) if lines else "处理完成。"
