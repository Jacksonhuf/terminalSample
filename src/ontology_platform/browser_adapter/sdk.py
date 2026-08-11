"""Python SDK for external agents to drive the Browser Adapter."""

from __future__ import annotations

import time
from typing import Any

import httpx

from ontology_platform.browser_adapter.schema import BrowserCommand, CreateSessionRequest, PageState


class BrowserAdapterClient:
    """HTTP client for /v1/browser — usable by OpenClaw, Hermes SKILL, scripts, etc."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout, headers=self._headers) as client:
            resp = client.request(method, url, **kwargs)
            if resp.status_code >= 400:
                raise RuntimeError(f"{resp.status_code} {resp.text[:300]}")
            if resp.headers.get("content-type", "").startswith("application/json"):
                return resp.json()
            return resp.text

    def create_session(
        self,
        *,
        mode: str = "interactive",
        start_url: str = "",
        script: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from ontology_platform.connector.browser.schema import BrowserScriptStep

        req = CreateSessionRequest(
            mode=mode,  # type: ignore[arg-type]
            start_url=start_url,
            script=[BrowserScriptStep.model_validate(s) for s in (script or [])],
            metadata=metadata or {},
            parameters=parameters or {},
        )
        return self._request("POST", "/v1/browser/sessions", json=req.model_dump())

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/browser/sessions/{session_id}")

    def cancel_session(self, session_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v1/browser/sessions/{session_id}")

    def send_command(
        self,
        session_id: str,
        command: BrowserCommand | dict[str, Any],
        *,
        wait_timeout_sec: float = 30.0,
    ) -> dict[str, Any]:
        cmd = command if isinstance(command, BrowserCommand) else BrowserCommand.model_validate(command)
        body = {"command": cmd.model_dump(), "wait_timeout_sec": wait_timeout_sec}
        return self._request("POST", f"/v1/browser/sessions/{session_id}/commands", json=body)

    def wait_step(
        self,
        session_id: str,
        *,
        after_version: int = 0,
        timeout_sec: float = 30.0,
    ) -> dict[str, Any] | None:
        data = self._request(
            "GET",
            f"/v1/browser/sessions/{session_id}/steps/wait",
            params={"after_version": after_version, "timeout_sec": timeout_sec},
        )
        if not data.get("ready"):
            return None
        return data.get("step")

    def snapshot(self, session_id: str, *, wait_timeout_sec: float = 30.0) -> PageState | None:
        result = self.send_command(
            session_id,
            BrowserCommand(action="snapshot"),
            wait_timeout_sec=wait_timeout_sec,
        )
        ps = result.get("page_state")
        return PageState.model_validate(ps) if ps else None

    def goto(self, session_id: str, url: str, *, wait_timeout_sec: float = 45.0) -> dict[str, Any]:
        return self.send_command(
            session_id,
            BrowserCommand(action="goto", url=url),
            wait_timeout_sec=wait_timeout_sec,
        )

    def click(self, session_id: str, selector: str, *, index: int = -1, wait_timeout_sec: float = 30.0) -> dict[str, Any]:
        return self.send_command(
            session_id,
            BrowserCommand(action="click", selector=selector, index=index),
            wait_timeout_sec=wait_timeout_sec,
        )

    def fill(
        self,
        session_id: str,
        selector: str,
        value: str,
        *,
        wait_timeout_sec: float = 30.0,
    ) -> dict[str, Any]:
        return self.send_command(
            session_id,
            BrowserCommand(action="fill", selector=selector, value=value),
            wait_timeout_sec=wait_timeout_sec,
        )

    def finish(
        self,
        session_id: str,
        data: list[dict[str, Any]] | None = None,
        *,
        wait_timeout_sec: float = 30.0,
    ) -> dict[str, Any]:
        return self.send_command(
            session_id,
            BrowserCommand(action="finish"),
            wait_timeout_sec=wait_timeout_sec,
        )

    def run_script(
        self,
        script: list[dict[str, Any]],
        *,
        start_url: str = "",
        metadata: dict[str, Any] | None = None,
        poll_interval_sec: float = 2.0,
        max_wait_sec: float = 300.0,
    ) -> dict[str, Any]:
        """Create scripted session and poll until completed (extension executes)."""
        created = self.create_session(
            mode="scripted",
            start_url=start_url,
            script=script,
            metadata=metadata,
        )
        session_id = created["session"]["id"]
        deadline = time.time() + max_wait_sec
        while time.time() < deadline:
            session = self.get_session(session_id)
            if session["status"] in ("completed", "failed", "cancelled"):
                return session
            time.sleep(poll_interval_sec)
        raise TimeoutError(f"script session {session_id} not finished within {max_wait_sec}s")


class InteractiveSession:
    """Context manager wrapping an interactive browser session."""

    def __init__(self, client: BrowserAdapterClient, session_id: str) -> None:
        self.client = client
        self.session_id = session_id
        self._step_version = 0

    def snapshot(self) -> PageState | None:
        return self.client.snapshot(self.session_id)

    def goto(self, url: str) -> dict[str, Any]:
        return self.client.goto(self.session_id, url)

    def click(self, selector: str, *, index: int = -1) -> dict[str, Any]:
        return self.client.click(self.session_id, selector, index=index)

    def fill(self, selector: str, value: str) -> dict[str, Any]:
        return self.client.fill(self.session_id, selector, value)

    def finish(self, data: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return self.client.finish(self.session_id, data)

    def close(self) -> None:
        try:
            self.client.cancel_session(self.session_id)
        except Exception:
            pass

    def __enter__(self) -> InteractiveSession:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def open_interactive_session(
    client: BrowserAdapterClient,
    *,
    start_url: str = "",
    metadata: dict[str, Any] | None = None,
) -> InteractiveSession:
    created = client.create_session(mode="interactive", start_url=start_url, metadata=metadata)
    return InteractiveSession(client, created["session"]["id"])
