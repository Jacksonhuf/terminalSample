"""Admin + browser_demo + simulated extension E2E."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_platform.admin.server import create_app

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def admin_client(tmp_path: Path) -> TestClient:
    connector_db = tmp_path / "connector.db"
    app = create_app(
        EXAMPLES,
        connector_db_path=connector_db,
        connectors_dir=EXAMPLES / "connectors",
    )
    return TestClient(app)


def _simulate_extension(client: TestClient, run_id: str) -> dict:
    body: dict = {}
    last: dict = {}
    for _ in range(12):
        resp = client.post(f"/v1/browser/sessions/{run_id}/steps", json=body)
        assert resp.status_code == 200
        last = resp.json()
        if last.get("done"):
            break
        action = (last.get("command") or {}).get("action")
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
                "records": [
                    {
                        "record_type": "page_snapshot",
                        "external_id": "example-home",
                        "payload": {"title": "Example Domain", "external_id": "example-home"},
                    }
                ],
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
    return last


def test_admin_browser_demo_simulated_extension(admin_client: TestClient):
    created = admin_client.post("/api/connectors/browser_demo/browser-run", json={"auto_sync": False})
    assert created.status_code == 200
    run_id = created.json()["run"]["id"]

    last = _simulate_extension(admin_client, run_id)
    assert last.get("done") is True

    final = admin_client.get(f"/api/browser/runs/{run_id}").json()
    assert final["status"] == "completed"
    assert final.get("records_captured", 0) >= 1
    assert final.get("completion", {}).get("records_captured", 0) >= 1

    staging = admin_client.get("/api/mappings/staging").json()
    connectors = {s.get("connector_name") for s in staging.get("summaries", [])}
    assert "browser_demo" in connectors
