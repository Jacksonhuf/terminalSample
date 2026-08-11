"""Tests for inline LLM API key on profile save."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ontology_platform.admin.llm_api import resolve_llm_api_key_ref
from ontology_platform.admin.server import create_app
from ontology_platform.connector.credential_store import CredentialStore

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def test_resolve_llm_api_key_ref_creates_credential(tmp_path: Path) -> None:
    db = tmp_path / "platform.db"
    cred_store = CredentialStore(db)
    ref = resolve_llm_api_key_ref(
        profile_id="llm-internal",
        profile_name="内网 Qwen",
        api_key_ref="",
        api_key="sk-test-token",
        credential_store=cred_store,
    )
    assert ref == "cred-llm-llm-internal"
    secret = cred_store.get_secret(ref)
    assert secret is not None
    assert secret.password == "sk-test-token"


def test_create_llm_profile_with_inline_api_key(tmp_path: Path) -> None:
    db = tmp_path / "platform.db"
    app = create_app(EXAMPLES_DIR, store_path=db)
    client = TestClient(app)

    res = client.post(
        "/api/llm/profiles",
        json={
            "id": "llm-newapi",
            "name": "New API Gateway",
            "model": "qwen-plus",
            "base_url": "http://10.0.0.1/v1",
            "api_key": "sk-inline-key",
            "proxy_mode": "bypass",
            "is_default": True,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["api_key_ref"] == "cred-llm-llm-newapi"

    list_res = client.get("/api/llm/profiles")
    profile = list_res.json()["profiles"][0]
    assert profile["api_key_set"] is True
