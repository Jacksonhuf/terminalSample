"""LLM-driven browser agent for Computer Use capture."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ontology_platform.connector.capture.browser import BrowserSession, PLAYWRIGHT_AVAILABLE
from ontology_platform.connector.capture.prompts import SYSTEM_PROMPT, build_step_prompt
from ontology_platform.connector.schema import CaptureBatch, CaptureRecord


class LlmCaptureAgent:
    """Multi-step LLM agent that drives a browser to extract capture records."""

    def __init__(
        self,
        chat_model: BaseChatModel,
        *,
        max_steps: int = 25,
        use_screenshot: bool = True,
    ) -> None:
        self.chat_model = chat_model
        self.max_steps = max_steps
        self.use_screenshot = use_screenshot and PLAYWRIGHT_AVAILABLE

    def run(self, task: dict[str, Any], credentials: dict[str, str]) -> CaptureBatch:
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("playwright 未安装，无法执行 LLM Computer Use 采集")

        history: list[str] = []
        login = task.get("login") or {}
        start_url = login.get("login_url") or task.get("source_url") or ""

        with BrowserSession(headless=True) as session:
            if start_url:
                session.goto(start_url)

            if credentials.get("CU_USERNAME") and login.get("password_provided"):
                self._attempt_login(session, login, credentials, history)

            target_url = task.get("source_url") or ""
            if target_url and session.page and session.page.url != target_url:
                session.goto(target_url)

            for step in range(1, self.max_steps + 1):
                page_state = session.page_snapshot()
                action = self._next_action(task, page_state, step, history)
                history.append(f"step {step}: {action.get('action')} - {action.get('thought', '')[:80]}")

                act = action.get("action")
                if act == "finish":
                    return self._build_batch(task, action.get("records") or [])

                if act == "click":
                    session.click_index(int(action.get("index", 0)))
                elif act == "type":
                    session.type_index(int(action.get("index", 0)), str(action.get("text", "")))
                elif act == "goto" and action.get("url"):
                    session.goto(str(action["url"]))
                elif act == "scroll":
                    session.scroll_down()
                elif act == "wait":
                    session.wait_short()
                else:
                    session.wait_short()

        raise RuntimeError(f"采集在 {self.max_steps} 步内未完成，请优化 capture_instructions 或增加步数")

    def _attempt_login(
        self,
        session: BrowserSession,
        login: dict[str, Any],
        credentials: dict[str, str],
        history: list[str],
    ) -> None:
        page_state = session.page_snapshot()
        username = credentials.get("CU_USERNAME", "")
        password = credentials.get("CU_PASSWORD", "")
        user_idx = self._find_input_index(page_state, login.get("username_field", "username"), username)
        pass_idx = self._find_input_index(page_state, login.get("password_field", "password"), "")
        if user_idx is not None:
            session.type_index(user_idx, username)
        if pass_idx is not None:
            session.type_index(pass_idx, password)
        submit_idx = self._find_submit_index(page_state)
        if submit_idx is not None:
            session.click_index(submit_idx)
            history.append("auto-login submitted")
            session.wait_short()

    def _find_input_index(self, page_state: dict[str, Any], field_name: str, hint: str) -> int | None:
        for el in page_state.get("elements", []):
            if el.get("tag") != "input":
                continue
            if el.get("name") == field_name or el.get("id") == field_name:
                return int(el["index"])
            if hint and hint.lower() in (el.get("text") or "").lower():
                return int(el["index"])
        for el in page_state.get("elements", []):
            if el.get("tag") == "input" and el.get("type") in ("text", "email", ""):
                return int(el["index"])
        return None

    def _find_submit_index(self, page_state: dict[str, Any]) -> int | None:
        for el in page_state.get("elements", []):
            if el.get("tag") == "button" or el.get("type") == "submit":
                text = (el.get("text") or "").lower()
                if any(k in text for k in ("login", "sign in", "登录", "submit")):
                    return int(el["index"])
        for el in page_state.get("elements", []):
            if el.get("tag") == "button":
                return int(el["index"])
        return None

    def _next_action(
        self,
        task: dict[str, Any],
        page_state: dict[str, Any],
        step: int,
        history: list[str],
    ) -> dict[str, Any]:
        prompt = build_step_prompt(task, page_state, step, self.max_steps, history)
        if self.use_screenshot:
            content = [{"type": "text", "text": prompt}]
        else:
            content = prompt

        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=content)]
        response = self.chat_model.invoke(messages)
        text = response.content if isinstance(response.content, str) else str(response.content)
        return self._parse_action_json(text)

    def _parse_action_json(self, text: str) -> dict[str, Any]:
        text = text.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise ValueError(f"LLM 未返回有效 JSON: {text[:200]}") from None

    def _build_batch(self, task: dict[str, Any], records_raw: list[Any]) -> CaptureBatch:
        records: list[CaptureRecord] = []
        for item in records_raw:
            if not isinstance(item, dict):
                continue
            record_type = str(item.get("record_type", "")).strip()
            external_id = str(item.get("external_id", "")).strip()
            payload = item.get("payload") or {}
            if not record_type or not external_id:
                continue
            records.append(
                CaptureRecord(
                    record_type=record_type,
                    external_id=external_id,
                    payload=dict(payload),
                )
            )
        if not records:
            raise ValueError("finish 动作未返回有效 records")
        return CaptureBatch(
            connector=str(task.get("connector", "")),
            run_id=task.get("run_id"),
            source_url=str(task.get("source_url", "")),
            records=records,
        )
