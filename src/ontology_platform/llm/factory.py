"""Build LangChain chat models from LLM configuration."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from ontology_platform.llm.proxy import build_httpx_client_kwargs, resolve_proxy_used
from ontology_platform.llm.schema import LlmProfile, LlmTestResult, ProxyConfig

if TYPE_CHECKING:
    from ontology_platform.agent.config import AgentConfig
    from ontology_platform.connector.credential_store import CredentialStore
    from ontology_platform.llm.store import LlmConfigStore


def _resolve_api_key(profile: LlmProfile, credential_store: CredentialStore | None) -> str:
    if not profile.api_key_ref or credential_store is None:
        return "not-needed"
    secret = credential_store.get_secret(profile.api_key_ref)
    if secret is None:
        return "not-needed"
    return secret.password or secret.username or "not-needed"


def build_chat_model(
    profile: LlmProfile,
    proxy_cfg: ProxyConfig,
    credential_store: CredentialStore | None = None,
) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    client_kwargs = build_httpx_client_kwargs(profile, proxy_cfg)
    api_key = _resolve_api_key(profile, credential_store)

    import httpx

    http_client = httpx.Client(**client_kwargs)
    http_async_client = httpx.AsyncClient(**client_kwargs)

    kwargs: dict = {
        "model": profile.model,
        "api_key": api_key,
        "temperature": profile.temperature,
        "max_tokens": profile.max_tokens,
        "http_client": http_client,
        "http_async_client": http_async_client,
    }
    if profile.base_url:
        kwargs["base_url"] = profile.base_url
    return ChatOpenAI(**kwargs)


def build_chat_model_from_store(
    llm_store: LlmConfigStore,
    credential_store: CredentialStore | None = None,
    profile_id: str | None = None,
) -> BaseChatModel | None:
    profile = (
        llm_store.get_profile(profile_id)
        if profile_id
        else llm_store.get_default_profile()
    )
    if profile is None or not profile.enabled:
        return None
    if not profile.model:
        return None
    proxy_cfg = llm_store.get_proxy_config()
    return build_chat_model(profile, proxy_cfg, credential_store)


def apply_planner_mode_from_profile(config: AgentConfig, profile: LlmProfile | None) -> None:
    if profile is None:
        return
    if profile.planner_mode != "auto" or config.planner_mode == "rule":
        config.planner_mode = profile.planner_mode


def test_llm_connection(
    profile: LlmProfile,
    proxy_cfg: ProxyConfig,
    credential_store: CredentialStore | None = None,
) -> LlmTestResult:
    try:
        model = build_chat_model(profile, proxy_cfg, credential_store)
        start = time.perf_counter()
        response = model.invoke([HumanMessage(content="ping")])
        latency_ms = int((time.perf_counter() - start) * 1000)
        content = response.content if isinstance(response.content, str) else str(response.content)
        return LlmTestResult(
            success=True,
            message="连接成功",
            latency_ms=latency_ms,
            proxy_used=resolve_proxy_used(profile, proxy_cfg),
            proxy_mode=profile.proxy_mode,
            model_response=content[:200],
        )
    except Exception as exc:
        return LlmTestResult(
            success=False,
            message=str(exc),
            proxy_used=resolve_proxy_used(profile, proxy_cfg),
            proxy_mode=profile.proxy_mode,
        )
