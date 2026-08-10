"""Admin API helpers for LLM configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ontology_platform.llm.schema import ProxyConfig


class SaveLlmProfileRequest(BaseModel):
    id: str = ""
    name: str
    provider: str = "openai_compatible"
    enabled: bool = True
    is_default: bool = False
    base_url: str = ""
    model: str = ""
    api_key_ref: str = ""
    planner_mode: str = "auto"
    proxy_mode: str = "inherit"
    temperature: float = 0.2
    timeout_sec: int = 60
    max_tokens: int = 4096


class SaveProxyConfigRequest(BaseModel):
    enabled: bool = False
    http_proxy: str = ""
    https_proxy: str = ""
    no_proxy: str = "localhost,127.0.0.1"
    internal_bypass_proxy: bool = True


def proxy_to_dict(config: ProxyConfig) -> dict:
    return config.model_dump()
