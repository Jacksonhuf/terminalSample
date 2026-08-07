"""LangGraph node implementations for the ontology agent."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt

from ontology_platform.agent.planner import Planner
from ontology_platform.agent.state import AgentState
from ontology_platform.ontology.service import OntologyService


def _last_user_message(state: AgentState) -> str:
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return ""


def make_plan_node(service: OntologyService, planner: Planner):
    """Classify intent and build execution plan."""

    def plan_node(state: AgentState) -> dict[str, Any]:
        message = _last_user_message(state)
        result = planner.plan(message, service)
        return {
            "intent": result.intent,
            "entities": result.entities,
            "plan": result.plan,
            "error": result.error,
            "approval_status": "",
            "requires_approval": False,
            "pending_action": {},
            "interrupted": False,
        }

    return plan_node


def make_executor_node(tools_by_name: dict[str, Any], approved: bool = False):
    """Execute the planned tool calls."""

    def executor(state: AgentState) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        requires_approval = False
        pending_action: dict[str, Any] = {}

        for step in state.get("plan", []):
            tool_name = step["tool"]
            tool = tools_by_name.get(tool_name)
            if tool is None:
                results.append({"tool": tool_name, "error": "Tool not found"})
                continue

            args = dict(step.get("args", {}))
            if tool_name == "execute_action" and approved:
                args["approved"] = True

            try:
                output = tool.invoke(args)
                parsed = json.loads(output) if isinstance(output, str) else output

                if isinstance(parsed, dict) and parsed.get("requires_approval"):
                    requires_approval = True
                    pending_action = {"tool": tool_name, "args": args}

                results.append({"tool": tool_name, "result": parsed})
            except Exception as exc:
                results.append({"tool": tool_name, "error": str(exc)})

        return {
            "ontology_results": results,
            "requires_approval": requires_approval,
            "pending_action": pending_action,
        }

    return executor


def make_approval_node():
    """Human-in-the-loop approval gate using LangGraph interrupt."""

    def approval_node(state: AgentState) -> dict[str, Any]:
        if state.get("approval_status") in ("approved", "rejected"):
            return {}

        pending = state.get("pending_action", {})
        action_name = pending.get("args", {}).get("action_name", "unknown")
        target_id = pending.get("args", {}).get("target_id", "")

        decision = interrupt(
            {
                "type": "approval_required",
                "message": f"操作 {action_name} 作用于 {target_id} 需要审批",
                "pending_action": pending,
            }
        )

        approved = decision if isinstance(decision, bool) else bool(
            decision.get("approved") if isinstance(decision, dict) else decision
        )
        return {
            "approval_status": "approved" if approved else "rejected",
            "interrupted": False,
        }

    return approval_node


def make_response_node(service: OntologyService):
    """Synthesize a natural language response from ontology results."""

    def respond(state: AgentState) -> dict[str, Any]:
        if state.get("approval_status") == "rejected":
            response = "操作已被拒绝，未执行任何变更。"
        elif state.get("error"):
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
        elif state.get("requires_approval") and not state.get("approval_status"):
            pending = state.get("pending_action", {})
            action = pending.get("args", {}).get("action_name", "操作")
            target = pending.get("args", {}).get("target_id", "")
            response = (
                f"⏸️ 操作「{action}」(目标: {target}) 需要审批。\n"
                f"请调用 resume(approved=True) 批准，或 resume(approved=False) 拒绝。"
            )
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
                lines.append("对象未找到。")
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
            elif not result.get("requires_approval"):
                lines.append(f"❌ {result.get('message', '操作失败')}")

        elif tool == "get_ontology_schema":
            lines.append("已加载本体 Schema。")

        else:
            lines.append(json.dumps(result, ensure_ascii=False, indent=2))

    return "\n".join(lines) if lines else "处理完成。"
