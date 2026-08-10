"""Prompt templates for LLM Computer Use capture."""

from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = """You are a web data capture agent. You browse pages and extract structured records.

Respond with ONLY valid JSON (no markdown fences). Schema:
{
  "thought": "brief reasoning",
  "action": "click|type|goto|scroll|wait|finish",
  "index": 0,
  "text": "text to type when action=type",
  "url": "url when action=goto",
  "records": []
}

Actions:
- click: click element by index from the page snapshot
- type: type text into input by index
- goto: navigate to url
- scroll: scroll down one page
- wait: wait 2 seconds
- finish: extraction complete; records must be a non-empty array

Each record in finish.records:
{
  "record_type": "<type from expected_record_types>",
  "external_id": "<unique id>",
  "payload": { ... }
}

Rules:
- Use finish only when you have extracted all visible data matching the instructions
- external_id must be stable (prefer id field from payload)
- Do not invent data not visible on the page
- If login is required, use provided credentials via click/type actions first
"""


def build_step_prompt(
    task: dict[str, Any],
    page_state: dict[str, Any],
    step: int,
    max_steps: int,
    history: list[str],
) -> str:
    login = task.get("login") or {}
    hints = task.get("hints") or []
    return f"""Capture task step {step}/{max_steps}

Connector: {task.get('connector')}
Target URL: {task.get('source_url')}
Expected record types: {json.dumps(task.get('expected_record_types', []), ensure_ascii=False)}

Login (if needed):
- login_url: {login.get('login_url', '')}
- username: {login.get('username', '')}
- password_provided: {login.get('password_provided', False)}

Instructions:
{task.get('instructions', '')}

Hints:
{chr(10).join('- ' + h for h in hints) if hints else '(none)'}

Recent actions:
{chr(10).join(history[-8:]) if history else '(none)'}

Current page:
{json.dumps(page_state, ensure_ascii=False, indent=2)}

Choose the next action as JSON."""
