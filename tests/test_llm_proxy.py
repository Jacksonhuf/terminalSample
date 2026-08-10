"""Tests for LLM proxy resolution."""

from __future__ import annotations

from ontology_platform.llm.proxy import (
    is_internal_host,
    resolve_proxy_used,
    should_bypass_proxy,
)
from ontology_platform.llm.schema import LlmProfile, ProxyConfig


def test_internal_host_detection() -> None:
    assert is_internal_host("127.0.0.1") is True
    assert is_internal_host("10.1.2.3") is True
    assert is_internal_host("api.openai.com") is False


def test_bypass_internal_url() -> None:
    proxy = ProxyConfig(enabled=True, http_proxy="http://proxy:8080", internal_bypass_proxy=True)
    assert should_bypass_proxy("http://10.0.0.5/v1", proxy) is True
    assert should_bypass_proxy("https://api.openai.com/v1", proxy) is False


def test_no_proxy_pattern() -> None:
    proxy = ProxyConfig(
        enabled=True,
        http_proxy="http://proxy:8080",
        no_proxy="localhost,.corp.internal",
        internal_bypass_proxy=False,
    )
    assert should_bypass_proxy("http://llm.corp.internal/v1", proxy) is True


def test_profile_proxy_modes() -> None:
    proxy = ProxyConfig(enabled=True, http_proxy="http://proxy:8080")
    internal = LlmProfile(
        id="x",
        name="x",
        base_url="http://10.0.0.1/v1",
        model="m",
        proxy_mode="bypass",
    )
    public = LlmProfile(
        id="y",
        name="y",
        base_url="https://api.openai.com/v1",
        model="m",
        proxy_mode="use_proxy",
    )
    assert resolve_proxy_used(internal, proxy) is False
    assert resolve_proxy_used(public, proxy) is True
