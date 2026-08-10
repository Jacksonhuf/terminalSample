"""Proxy resolution for LLM HTTP clients."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from ontology_platform.llm.schema import LlmProfile, ProxyConfig


def _parse_no_proxy(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _host_matches_no_proxy(host: str, patterns: list[str]) -> bool:
    host = host.lower()
    for pattern in patterns:
        if pattern.startswith(".") and host.endswith(pattern):
            return True
        if host == pattern:
            return True
        if pattern.startswith("*.") and host.endswith(pattern[1:]):
            return True
    return False


def is_internal_host(host: str) -> bool:
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


def should_bypass_proxy(base_url: str, proxy_cfg: ProxyConfig) -> bool:
    if not base_url:
        return False
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    if proxy_cfg.internal_bypass_proxy and is_internal_host(host):
        return True
    patterns = _parse_no_proxy(proxy_cfg.no_proxy)
    return _host_matches_no_proxy(host, patterns)


def resolve_proxy_used(profile: LlmProfile, proxy_cfg: ProxyConfig) -> bool:
    if profile.proxy_mode == "bypass":
        return False
    if profile.proxy_mode == "use_proxy":
        return proxy_cfg.enabled and bool(proxy_cfg.http_proxy or proxy_cfg.https_proxy)
    if profile.proxy_mode == "inherit":
        if should_bypass_proxy(profile.base_url, proxy_cfg):
            return False
        return proxy_cfg.enabled and bool(proxy_cfg.http_proxy or proxy_cfg.https_proxy)
    return False


def build_httpx_proxy_url(proxy_cfg: ProxyConfig) -> str | None:
    if not proxy_cfg.enabled:
        return None
    return proxy_cfg.https_proxy or proxy_cfg.http_proxy or None


def build_httpx_client_kwargs(profile: LlmProfile, proxy_cfg: ProxyConfig) -> dict:
    """Return kwargs for httpx.Client(proxy=..., trust_env=False)."""
    use_proxy = resolve_proxy_used(profile, proxy_cfg)
    proxy_url = build_httpx_proxy_url(proxy_cfg) if use_proxy else None
    return {
        "proxy": proxy_url,
        "trust_env": False,
        "timeout": profile.timeout_sec,
    }
