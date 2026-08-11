"""Translate scripted steps and agent loop into BrowserCommand sequences."""

from __future__ import annotations

import re
from typing import Any

from ontology_platform.connector.browser.schema import (
    BrowserCommand,
    BrowserScriptStep,
    BrowserStepRequest,
    PageState,
)


def _render(template: str, ctx: dict[str, Any]) -> str:
    if not template:
        return template

    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        val = ctx.get(key, "")
        return "" if val is None else str(val)

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", repl, template)


def script_step_to_command(step: BrowserScriptStep, ctx: dict[str, Any]) -> BrowserCommand:
    return BrowserCommand(
        action=step.action,
        selector=_render(step.selector, ctx),
        url=_render(step.url, ctx),
        text=_render(step.text, ctx),
        value=_render(step.value, ctx),
        index=step.index,
        ms=step.ms,
        field=step.field,
        record_type=step.record_type,
        external_id=_render(step.external_id, ctx),
    )


def next_scripted_command(
    steps: list[dict[str, Any]],
    step_index: int,
    ctx: dict[str, Any],
) -> tuple[BrowserCommand | None, int, bool]:
    if step_index >= len(steps):
        return BrowserCommand(action="finish", message="script complete"), step_index, True
    step = BrowserScriptStep.model_validate(steps[step_index])
    cmd = script_step_to_command(step, ctx)
    done = step.action == "finish"
    return cmd, step_index + 1, done


def next_agent_loop_command(
    *,
    page_state: PageState | None,
    step_index: int,
    source_url: str,
    instructions: str,
    expected_record_types: list[str],
) -> tuple[BrowserCommand | None, int, bool]:
    """Minimal agent loop without LLM: navigate → snapshot → finish placeholder."""
    if step_index == 0 and source_url:
        if not page_state or not page_state.url.startswith(source_url.split("?")[0][:20]):
            return BrowserCommand(action="goto", url=source_url), 1, False
        return BrowserCommand(action="snapshot"), 1, False
    if step_index == 1:
        return (
            BrowserCommand(
                action="finish",
                message=(
                    "Agent loop 占位：请在 Connector 中配置 browser_actions 使用 scripted 模式，"
                    "或接入 LLM step planner。当前 instructions: "
                    + (instructions[:120] if instructions else "(无)")
                ),
                record_type=expected_record_types[0] if expected_record_types else "",
            ),
            2,
            True,
        )
    return BrowserCommand(action="finish"), step_index, True


def merge_step_records(
    existing: list[dict[str, Any]],
    request: BrowserStepRequest,
    page_state: PageState | None,
) -> list[dict[str, Any]]:
    records = list(existing)
    for raw in request.records:
        records.append(raw)
    if page_state and page_state.extracted:
        ext_id = str(page_state.extracted.get("external_id") or page_state.url or "extract")
        records.append(
            {
                "record_type": page_state.extracted.get("record_type", "page_extract"),
                "external_id": ext_id,
                "payload": dict(page_state.extracted),
            }
        )
    return records
