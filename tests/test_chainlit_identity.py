"""Tests for Chainlit identity resolution."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ontology_platform.chat.identity import _roles_from_user, resolve_approver_identity, resolve_chainlit_identity


class TestChainlitIdentity:
    def test_roles_from_user_metadata(self, monkeypatch):
        monkeypatch.delenv("ONTOLOGY_ROLE_MAP", raising=False)
        user = SimpleNamespace(identifier="zhangsan", metadata={"roles": ["admin", "operator"]})
        assert _roles_from_user(user) == ["admin", "operator"]

    def test_roles_from_role_map(self, monkeypatch):
        monkeypatch.setenv("ONTOLOGY_ROLE_MAP", '{"zhang": ["admin"], "li": ["operator"]}')
        user = SimpleNamespace(identifier="zhangsan", metadata={})
        assert _roles_from_user(user) == ["admin"]

    def test_resolve_chainlit_identity_fallback(self, monkeypatch):
        monkeypatch.setenv("ONTOLOGY_USER_ID", "dev-user")
        monkeypatch.setenv("ONTOLOGY_USER_ROLES", "operator,viewer")
        with patch("ontology_platform.chat.identity.cl.user_session") as session:
            session.get.return_value = None
            user_id, roles = resolve_chainlit_identity()
        assert user_id == "dev-user"
        assert roles == ["operator", "viewer"]

    def test_resolve_approver_identity_fallback(self, monkeypatch):
        monkeypatch.setenv("ONTOLOGY_USER_ID", "anonymous")
        monkeypatch.setenv("ONTOLOGY_APPROVER_ROLES", "admin")
        with patch("ontology_platform.chat.identity.cl.user_session") as session:
            session.get.return_value = None
            user_id, roles = resolve_approver_identity()
        assert user_id == "anonymous"
        assert roles == ["admin"]
