"""LLM profile and proxy configuration schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

PlannerMode = Literal["rule", "llm", "auto"]
Provider = Literal["openai_compatible", "openai", "azure", "anthropic"]
ProxyMode = Literal["inherit", "use_proxy", "bypass"]


class ProxyConfig(BaseModel):
    enabled: bool = False
    http_proxy: str = ""
    https_proxy: str = ""
    no_proxy: str = "localhost,127.0.0.1"
    internal_bypass_proxy: bool = True


class LlmProfile(BaseModel):
    id: str
    name: str
    provider: Provider = "openai_compatible"
    enabled: bool = True
    is_default: bool = False
    base_url: str = ""
    model: str = ""
    api_key_ref: str = ""
    planner_mode: PlannerMode = "auto"
    proxy_mode: ProxyMode = "inherit"
    temperature: float = 0.2
    timeout_sec: int = 60
    max_tokens: int = 4096
    created_at: str = ""
    updated_at: str = ""


class LlmProfilePublic(BaseModel):
    id: str
    name: str
    provider: Provider = "openai_compatible"
    enabled: bool = True
    is_default: bool = False
    base_url: str = ""
    model: str = ""
    api_key_ref: str = ""
    api_key_set: bool = False
    planner_mode: PlannerMode = "auto"
    proxy_mode: ProxyMode = "inherit"
    temperature: float = 0.2
    timeout_sec: int = 60
    max_tokens: int = 4096
    created_at: str = ""
    updated_at: str = ""


class LlmTestResult(BaseModel):
    success: bool
    message: str = ""
    latency_ms: int = 0
    proxy_used: bool = False
    proxy_mode: str = ""
    model_response: str = ""
