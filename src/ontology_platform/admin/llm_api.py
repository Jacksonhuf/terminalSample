"""Admin API helpers for LLM configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from ontology_platform.llm.schema import ProxyConfig

if TYPE_CHECKING:
    from ontology_platform.connector.credential_store import CredentialStore


class SaveLlmProfileRequest(BaseModel):
    id: str = ""
    name: str
    provider: str = "openai_compatible"
    enabled: bool = True
    is_default: bool = False
    base_url: str = ""
    model: str = ""
    api_key_ref: str = ""
    api_key: str = ""  # optional inline key; stored encrypted in credential store
    planner_mode: str = "auto"
    proxy_mode: str = "inherit"
    temperature: float = 0.2
    timeout_sec: int = 60
    max_tokens: int = 4096


def resolve_llm_api_key_ref(
    *,
    profile_id: str,
    profile_name: str,
    api_key_ref: str,
    api_key: str,
    credential_store: CredentialStore | None,
) -> str:
    """Create or update encrypted credential when api_key is provided."""
    key = (api_key or "").strip()
    if not key:
        return api_key_ref
    if credential_store is None:
        raise ValueError("未配置凭据存储路径，请使用 --store-path 启动，或在凭据库中预先创建 API Key")

    ref = (api_key_ref or "").strip() or f"cred-llm-{profile_id}"
    existing = credential_store.get_public(ref)
    if existing is None:
        credential_store.create(
            name=f"LLM API Key · {profile_name}",
            username="api",
            password=key,
            credential_id=ref,
            notes="Auto-created from LLM profile settings",
        )
    else:
        credential_store.rotate_password(ref, key)
    return ref


class SaveProxyConfigRequest(BaseModel):
    enabled: bool = False
    http_proxy: str = ""
    https_proxy: str = ""
    no_proxy: str = "localhost,127.0.0.1"
    internal_bypass_proxy: bool = True


def proxy_to_dict(config: ProxyConfig) -> dict:
    return config.model_dump()
