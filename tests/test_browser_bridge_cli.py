"""Tests for standalone Browser Bridge CLI."""

from fastapi.testclient import TestClient

from ontology_platform.browser_adapter.__main__ import create_bridge_app


def test_bridge_health(tmp_path):
    app = create_bridge_app(tmp_path / "bridge.db")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "browser-bridge"


def test_bridge_v1_sessions(tmp_path):
    app = create_bridge_app(tmp_path / "bridge.db")
    client = TestClient(app)
    resp = client.post(
        "/v1/browser/sessions",
        json={"mode": "scripted", "start_url": "https://example.com", "script": [{"action": "finish"}]},
    )
    assert resp.status_code == 200
    assert "session" in resp.json()
