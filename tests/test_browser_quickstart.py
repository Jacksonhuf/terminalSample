"""Tests for browser quickstart and collected_data in session API."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ontology_platform.browser_adapter.__main__ import create_bridge_app
from ontology_platform.browser_adapter.cli_quickstart import _demo_script


def test_demo_script_loads():
    script, start_url = _demo_script()
    assert start_url
    assert any(s.get("action") == "extract" for s in script)


def test_get_session_includes_collected_data(tmp_path):
    app = create_bridge_app(tmp_path / "bridge.db")
    client = TestClient(app)
    created = client.post(
        "/v1/browser/sessions",
        json={
            "mode": "scripted",
            "start_url": "https://example.com",
            "script": [{"action": "finish"}],
        },
    )
    session_id = created.json()["session"]["id"]

    # Simulate extension submitting records on finish
    client.post(
        f"/v1/browser/sessions/{session_id}/steps",
        json={
            "records": [
                {
                    "record_type": "page_snapshot",
                    "external_id": "x1",
                    "payload": {"title": "Hello"},
                }
            ],
            "step_result": {"action": "finish"},
        },
    )

    detail = client.get(f"/v1/browser/sessions/{session_id}").json()
    assert detail["status"] == "completed"
    assert detail["data_count"] >= 1
    assert len(detail.get("collected_data", [])) >= 1
    assert detail["collected_data"][0]["payload"]["title"] == "Hello"
