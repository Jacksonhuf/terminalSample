"""Simulate Chrome extension step loop for tests and --simulate runs."""

from __future__ import annotations

from typing import Any

import httpx


def _example_extract_record() -> dict[str, Any]:
    return {
        "record_type": "page_snapshot",
        "external_id": "example-home",
        "payload": {"title": "Example Domain", "external_id": "example-home"},
    }


def run_extension_simulation(
    base_url: str,
    *,
    api: str = "v1",
    run_id: str | None = None,
    max_steps: int = 12,
) -> dict[str, Any]:
    """Drive pending browser session through scripted steps (no real Chrome)."""
    base = base_url.rstrip("/")
    client = httpx.Client(timeout=30.0)

    if run_id is None:
        if api == "v1":
            pending = client.get(f"{base}/v1/browser/sessions/pending?limit=1").json()
            sessions = pending.get("sessions") or []
            if not sessions:
                raise RuntimeError("no pending v1 sessions")
            run_id = sessions[0]["id"]
        else:
            pending = client.get(f"{base}/api/browser/runs/pending?limit=1").json()
            runs = pending.get("runs") or []
            if not runs:
                raise RuntimeError("no pending legacy runs")
            run_id = runs[0]["id"]

    body: dict[str, Any] = {}
    last: dict[str, Any] = {}

    for _ in range(max_steps):
        if api == "v1":
            resp = client.post(f"{base}/v1/browser/sessions/{run_id}/steps", json=body)
        else:
            resp = client.post(f"{base}/api/browser/runs/{run_id}/step", json=body)
        resp.raise_for_status()
        last = resp.json()
        if last.get("done"):
            break

        cmd = last.get("command") or {}
        action = cmd.get("action")
        if action == "extract":
            body = {
                "page_state": {
                    "url": "https://example.com",
                    "title": "Example Domain",
                    "elements": [],
                    "tables": [],
                    "extracted": {"title": "Example Domain", "external_id": "example-home"},
                },
                "step_result": {"action": "extract"},
                "records": [_example_extract_record()],
            }
        elif action == "finish":
            body = {
                "page_state": {"url": "https://example.com", "title": "Example Domain"},
                "step_result": {"action": "finish"},
                "records": [],
            }
        else:
            body = {
                "page_state": {"url": "https://example.com", "title": "Example Domain"},
                "step_result": {"action": action or "noop"},
                "records": [],
            }

    if api == "v1":
        detail = client.get(f"{base}/v1/browser/sessions/{run_id}").json()
    else:
        detail = client.get(f"{base}/api/browser/runs/{run_id}").json()

    return {"run_id": run_id, "last_step": last, "session": detail}
