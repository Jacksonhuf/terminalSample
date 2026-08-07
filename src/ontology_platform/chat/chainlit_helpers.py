"""Chainlit UI helpers for the ontology agent platform."""

from __future__ import annotations

import json
from typing import Any

from ontology_platform.platform import ChatResult


def format_plan_steps(plan: list[dict[str, Any]]) -> str:
    if not plan:
        return "无执行计划"
    lines = []
    for i, step in enumerate(plan, 1):
        tool = step.get("tool", "?")
        args = json.dumps(step.get("args", {}), ensure_ascii=False)
        lines.append(f"{i}. `{tool}` — {args}")
    return "\n".join(lines)


def format_ontology_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "无执行结果"
    lines = []
    for item in results:
        tool = item.get("tool", "?")
        if "error" in item:
            lines.append(f"- **{tool}**: ❌ {item['error']}")
            continue
        result = item.get("result")
        if isinstance(result, dict) and result.get("requires_approval"):
            lines.append(f"- **{tool}**: ⏸️ 需要审批")
        elif isinstance(result, list):
            lines.append(f"- **{tool}**: 返回 {len(result)} 条记录")
        elif isinstance(result, dict):
            preview = json.dumps(result, ensure_ascii=False)[:200]
            lines.append(f"- **{tool}**: {preview}")
        else:
            lines.append(f"- **{tool}**: 完成")
    return "\n".join(lines)


def format_pending_action(pending: dict[str, Any]) -> str:
    if not pending:
        return "无待审批操作"
    args = pending.get("args", {})
    return (
        f"**动作**: {args.get('action_name', '未知')}\n"
        f"**目标**: {args.get('target_id', '未知')}\n"
        f"**参数**: `{json.dumps(args.get('parameters', {}), ensure_ascii=False)}`"
    )


def summarize_chat_result(result: ChatResult) -> dict[str, str]:
    """Build step outputs for Chainlit UI."""
    return {
        "intent": result.intent or "unknown",
        "plan": format_plan_steps(result.plan),
        "execution": format_ontology_results(result.ontology_results),
        "response": result.response,
        "approval": format_pending_action(result.pending_action) if result.interrupted else "",
    }
