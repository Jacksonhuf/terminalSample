"""Tests for Chainlit helper utilities."""

from ontology_platform.chat.chainlit_helpers import (
    format_pending_action,
    format_plan_steps,
    summarize_chat_result,
)
from ontology_platform.platform import ChatResult


def test_format_plan_steps():
    plan = [
        {"tool": "search_objects", "args": {"object_type": "Prototype", "filters": {}}},
        {"tool": "get_object", "args": {"object_type": "Prototype", "object_id": "SN-001"}},
    ]
    text = format_plan_steps(plan)
    assert "search_objects" in text
    assert "get_object" in text


def test_format_pending_action():
    pending = {
        "tool": "execute_action",
        "args": {
            "action_name": "ReservePrototype",
            "target_id": "SN-2024-001",
            "parameters": {"person_id": "P-001"},
        },
    }
    text = format_pending_action(pending)
    assert "ReservePrototype" in text
    assert "SN-2024-001" in text


def test_summarize_chat_result():
    result = ChatResult(
        response="找到 2 个对象",
        intent="query",
        plan=[{"tool": "search_objects", "args": {"object_type": "Prototype"}}],
        ontology_results=[{"tool": "search_objects", "result": [{"object_id": "SN-1"}]}],
    )
    summary = summarize_chat_result(result)
    assert summary["intent"] == "query"
    assert "search_objects" in summary["plan"]
    assert "找到" in summary["response"] or "返回" in summary["execution"]
