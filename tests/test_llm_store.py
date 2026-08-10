"""Tests for LLM config store."""

from __future__ import annotations

from pathlib import Path

from ontology_platform.connector.credential_store import CredentialStore
from ontology_platform.llm.store import LlmConfigStore


def test_llm_store_crud(tmp_path: Path) -> None:
    store = LlmConfigStore(tmp_path / "platform.db")
    cred = store.create_profile(
        name="Internal Qwen",
        profile_id="llm-internal",
        base_url="http://10.0.0.1/v1",
        model="qwen",
        proxy_mode="bypass",
        is_default=True,
    )
    assert cred.id == "llm-internal"
    assert cred.is_default is True

    updated = store.update_profile("llm-internal", name="Qwen Internal")
    assert updated is not None
    assert updated.name == "Qwen Internal"

    default = store.get_default_profile()
    assert default is not None
    assert default.id == "llm-internal"

    assert store.delete_profile("llm-internal") is True


def test_proxy_config_persist(tmp_path: Path) -> None:
    store = LlmConfigStore(tmp_path / "platform.db")
    from ontology_platform.llm.schema import ProxyConfig

    store.save_proxy_config(
        ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.corp:8080",
            no_proxy="localhost,.internal",
            internal_bypass_proxy=True,
        )
    )
    reloaded = LlmConfigStore(tmp_path / "platform.db")
    proxy = reloaded.get_proxy_config()
    assert proxy.enabled is True
    assert proxy.http_proxy == "http://proxy.corp:8080"


def test_api_key_set_flag(tmp_path: Path) -> None:
    db = tmp_path / "platform.db"
    cred_store = CredentialStore(db)
    cred_store.create(name="LLM Key", username="api", password="sk-test", credential_id="cred-llm")
    llm_store = LlmConfigStore(db)
    profile = llm_store.create_profile(
        name="OpenAI",
        profile_id="llm-openai",
        model="gpt-4o-mini",
        api_key_ref="cred-llm",
    )
    public = llm_store.list_profiles(cred_store)[0]
    assert public.api_key_set is True
    assert profile.api_key_ref == "cred-llm"
