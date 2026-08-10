"""Admin API tests for LLM configuration."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ontology_platform.admin.server import create_app

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


class TestLlmAdminAPI:
    def test_llm_unconfigured(self):
        app = create_app(EXAMPLES_DIR)
        client = TestClient(app)
        res = client.get("/api/llm/profiles")
        assert res.status_code == 200
        assert res.json()["configured"] is False

    def test_llm_profile_crud(self, tmp_path: Path):
        db = tmp_path / "platform.db"
        app = create_app(EXAMPLES_DIR, store_path=db)
        client = TestClient(app)

        create_res = client.post(
            "/api/llm/profiles",
            json={
                "name": "Internal",
                "id": "llm-test",
                "model": "qwen",
                "base_url": "http://10.0.0.1/v1",
                "proxy_mode": "bypass",
                "planner_mode": "auto",
                "is_default": True,
            },
        )
        assert create_res.status_code == 200
        assert create_res.json()["proxy_mode"] == "bypass"

        list_res = client.get("/api/llm/profiles")
        assert list_res.json()["count"] == 1

        active = client.get("/api/llm/active")
        assert active.json()["active"]["id"] == "llm-test"
        assert active.json()["proxy_will_be_used"] is False

        proxy_res = client.put(
            "/api/llm/proxy",
            json={
                "enabled": True,
                "http_proxy": "http://proxy:8080",
                "https_proxy": "http://proxy:8080",
                "no_proxy": "localhost",
                "internal_bypass_proxy": True,
            },
        )
        assert proxy_res.status_code == 200

        delete_res = client.delete("/api/llm/profiles/llm-test")
        assert delete_res.status_code == 200
