"""Build LangChain chat models from LLM configuration."""

from __future__ import annotations

import concurrent.futures
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


def _invoke_ping(model: BaseChatModel) -> str:
    response = model.invoke([HumanMessage(content="ping")])
    content = response.content if isinstance(response.content, str) else str(response.content)
    return content


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


def diagnose_llm_profile(
    profile: LlmProfile,
    proxy_cfg: ProxyConfig,
    credential_store: CredentialStore | None = None,
) -> dict:
    """Return config summary without any outbound network call."""
    api_key_ref = profile.api_key_ref or ""
    api_key_set = False
    if api_key_ref and credential_store is not None:
        api_key_set = credential_store.get_secret(api_key_ref) is not None
    return {
        "profile_id": profile.id,
        "base_url": profile.base_url,
        "model": profile.model,
        "timeout_sec": profile.timeout_sec,
        "proxy_mode": profile.proxy_mode,
        "proxy_will_be_used": resolve_proxy_used(profile, proxy_cfg),
        "api_key_ref": api_key_ref,
        "api_key_set": api_key_set,
        "hint": (
            "测试由 Admin 服务端发起访问 Base URL，请确认运行 ontology-admin 的机器能访问该内网地址"
        ),
    }


def preflight_llm_connection(
    profile: LlmProfile,
    proxy_cfg: ProxyConfig,
    credential_store: CredentialStore | None = None,
) -> LlmTestResult:
    """Quick reachability check to gateway /models without chat invoke."""
    import httpx

    proxy_used = resolve_proxy_used(profile, proxy_cfg)
    api_key = _resolve_api_key(profile, credential_store)
    if not profile.base_url:
        return LlmTestResult(
            success=False,
            message="未配置 Base URL",
            proxy_used=proxy_used,
            proxy_mode=profile.proxy_mode,
        )
    if api_key == "not-needed" and profile.api_key_ref:
        return LlmTestResult(
            success=False,
            message=f"API Key 凭据无效或未找到: {profile.api_key_ref}",
            proxy_used=proxy_used,
            proxy_mode=profile.proxy_mode,
        )
    url = profile.base_url.rstrip("/") + "/models"
    client_kwargs = build_httpx_client_kwargs(profile, proxy_cfg)
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout_sec = max(int(profile.timeout_sec or 60), 5)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_preflight_get, url, headers, client_kwargs)
            resp, latency_ms = future.result(timeout=timeout_sec + 5)
        if resp.status_code == 200:
            return LlmTestResult(
                success=True,
                message=f"网关可达 ({resp.status_code})",
                latency_ms=latency_ms,
                proxy_used=proxy_used,
                proxy_mode=profile.proxy_mode,
                model_response=resp.text[:200],
            )
        return LlmTestResult(
            success=False,
            message=f"网关返回 HTTP {resp.status_code}: {resp.text[:300]}",
            latency_ms=latency_ms,
            proxy_used=proxy_used,
            proxy_mode=profile.proxy_mode,
        )
    except concurrent.futures.TimeoutError:
        return LlmTestResult(
            success=False,
            message=f"网关连接超时（>{timeout_sec} 秒）: {url}",
            proxy_used=proxy_used,
            proxy_mode=profile.proxy_mode,
        )
    except Exception as exc:
        return LlmTestResult(
            success=False,
            message=f"无法连接网关 {url}: {exc}",
            proxy_used=proxy_used,
            proxy_mode=profile.proxy_mode,
        )


def _preflight_get(url: str, headers: dict, client_kwargs: dict):
    import httpx

    start = time.perf_counter()
    with httpx.Client(**client_kwargs) as client:
        resp = client.get(url, headers=headers)
    latency_ms = int((time.perf_counter() - start) * 1000)
    return resp, latency_ms


def test_llm_connection(
    profile: LlmProfile,
    proxy_cfg: ProxyConfig,
    credential_store: CredentialStore | None = None,
) -> LlmTestResult:
    proxy_used = resolve_proxy_used(profile, proxy_cfg)
    api_key_ref = profile.api_key_ref or ""
    if api_key_ref and credential_store is None:
        return LlmTestResult(
            success=False,
            message="未配置凭据存储（请使用 --store-path 启动 Admin）",
            proxy_used=proxy_used,
            proxy_mode=profile.proxy_mode,
        )
    if api_key_ref and credential_store is not None and credential_store.get_secret(api_key_ref) is None:
        return LlmTestResult(
            success=False,
            message=f"API Key 凭据不存在: {api_key_ref}",
            proxy_used=proxy_used,
            proxy_mode=profile.proxy_mode,
        )
    timeout_sec = max(int(profile.timeout_sec or 60), 5)
    try:
        model = build_chat_model(profile, proxy_cfg, credential_store)
        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_invoke_ping, model)
            content = future.result(timeout=timeout_sec + 5)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return LlmTestResult(
            success=True,
            message="连接成功",
            latency_ms=latency_ms,
            proxy_used=proxy_used,
            proxy_mode=profile.proxy_mode,
            model_response=content[:200],
        )
    except concurrent.futures.TimeoutError:
        return LlmTestResult(
            success=False,
            message=f"连接超时（>{timeout_sec} 秒），请检查 Base URL、代理设置与内网连通性",
            proxy_used=proxy_used,
            proxy_mode=profile.proxy_mode,
        )
    except Exception as exc:
        return LlmTestResult(
            success=False,
            message=str(exc),
            proxy_used=proxy_used,
            proxy_mode=profile.proxy_mode,
        )
