"""Tests for generic Browser Adapter bridge and agent SDK."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_platform.browser_adapter.bridge import build_browser_bridge
from ontology_platform.browser_adapter.schema import (
    BrowserCommand,
    CreateSessionRequest,
    PageState,
    SendCommandRequest,
    StepSubmitRequest,
)
from ontology_platform.browser_adapter.api import build_browser_router
from ontology_platform.connector.browser.schema import BrowserScriptStep

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def bridge(tmp_path: Path):
    return build_browser_bridge(tmp_path / "bridge.db")


@pytest.fixture
def client(bridge, tmp_path: Path):
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(build_browser_router(bridge))
    return TestClient(app)


class TestGenericBridge:
    def test_create_scripted_session(self, bridge):
        req = CreateSessionRequest(
            mode="scripted",
            start_url="https://example.com",
            script=[
                BrowserScriptStep(action="goto", url="{{start_url}}"),
                BrowserScriptStep(action="snapshot"),
                BrowserScriptStep(action="finish"),
            ],
            parameters={"start_url": "https://example.com"},
            metadata={"source": "test"},
        )
        result = bridge.create_session(req)
        assert result["session"]["mode"] == "scripted"
        assert result["initial_command"]["action"] == "goto"

    def test_scripted_step_loop_via_api(self, client):
        script = [
            {"action": "goto", "url": "https://example.com"},
            {"action": "wait", "ms": 100},
            {"action": "finish"},
        ]
        created = client.post(
            "/v1/browser/sessions",
            json={"mode": "scripted", "start_url": "https://example.com", "script": script},
        )
        assert created.status_code == 200
        sid = created.json()["session"]["id"]

        r1 = client.post(f"/v1/browser/sessions/{sid}/steps", json={})
        assert r1.status_code == 200
        assert r1.json()["command"]["action"] == "goto"
        assert r1.json()["done"] is False

        body = {
            "page_state": {"url": "https://example.com", "title": "Example"},
            "step_result": {"action": "goto"},
        }
        done = False
        for _ in range(6):
            r = client.post(f"/v1/browser/sessions/{sid}/steps", json=body)
            assert r.status_code == 200
            if r.json()["done"]:
                done = True
                break
            body = {
                "page_state": {"url": "https://example.com", "title": "Example"},
                "step_result": {"action": r.json()["command"]["action"]},
            }
        assert done

        session = client.get(f"/v1/browser/sessions/{sid}")
        assert session.json()["status"] == "completed"

    def test_list_pending_v1(self, client):
        client.post(
            "/v1/browser/sessions",
            json={"mode": "scripted", "start_url": "https://example.com", "script": [{"action": "finish"}]},
        )
        pending = client.get("/v1/browser/sessions/pending")
        assert pending.status_code == 200
        assert pending.json()["count"] >= 1

    def test_interactive_send_command_with_simulated_extension(self, bridge):
        created = bridge.create_session(
            CreateSessionRequest(mode="interactive", start_url="https://example.com")
        )
        sid = created["session"]["id"]

        import threading

        def extension_worker():
            # wait for agent to queue command
            import time
            for _ in range(50):
                row = bridge.store.get_row(sid)
                if row and row.get("pending_command_json"):
                    break
                time.sleep(0.05)
            resp = bridge.process_step(sid, StepSubmitRequest())
            assert resp.command is not None
            assert resp.command.action == "snapshot"
            bridge.process_step(
                sid,
                StepSubmitRequest(
                    page_state=PageState(url="https://example.com", title="Example"),
                    step_result={"action": "snapshot"},
                ),
            )

        worker = threading.Thread(target=extension_worker)
        worker.start()

        result = bridge.send_command(
            sid,
            SendCommandRequest(command=BrowserCommand(action="snapshot"), wait_timeout_sec=5.0),
        )
        worker.join(timeout=6)
        assert result.page_state is not None
        assert result.page_state.url == "https://example.com"

    def test_cancel_session(self, client):
        created = client.post(
            "/v1/browser/sessions",
            json={"mode": "interactive", "start_url": "https://example.com"},
        )
        sid = created.json()["session"]["id"]
        resp = client.delete(f"/v1/browser/sessions/{sid}")
        assert resp.status_code == 200
        session = client.get(f"/v1/browser/sessions/{sid}")
        assert session.json()["status"] == "cancelled"
