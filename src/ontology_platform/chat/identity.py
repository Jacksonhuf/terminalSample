"""Resolve user identity and roles for Chainlit sessions."""

from __future__ import annotations

import json
import os
from typing import Any

import chainlit as cl


def _parse_roles(raw: str) -> list[str]:
    return [r.strip() for r in raw.split(",") if r.strip()]


def _roles_from_user(user: Any) -> list[str]:
    metadata = getattr(user, "metadata", None) or {}
    if isinstance(metadata, dict) and metadata.get("roles"):
        roles = metadata["roles"]
        if isinstance(roles, str):
            return _parse_roles(roles)
        if isinstance(roles, list):
            return [str(r) for r in roles]
    role_map_raw = os.getenv("ONTOLOGY_ROLE_MAP", "")
    if role_map_raw:
        try:
            role_map: dict[str, list[str]] = json.loads(role_map_raw)
            identifier = (
                getattr(user, "identifier", None)
                or getattr(user, "id", None)
                or ""
            )
            for prefix, mapped_roles in role_map.items():
                if identifier.startswith(prefix):
                    return mapped_roles
        except json.JSONDecodeError:
            pass
    return _parse_roles(os.getenv("ONTOLOGY_USER_ROLES", "operator"))


def resolve_chainlit_identity() -> tuple[str, list[str]]:
    """Return (user_id, roles) for the current Chainlit session."""
    user = cl.user_session.get("user")
    if user is not None:
        user_id = (
            getattr(user, "identifier", None)
            or getattr(user, "id", None)
            or getattr(user, "display_name", None)
            or "anonymous"
        )
        return str(user_id), _roles_from_user(user)

    user_id = os.getenv("ONTOLOGY_USER_ID", "anonymous")
    roles = _parse_roles(os.getenv("ONTOLOGY_USER_ROLES", "operator"))
    return user_id, roles


def resolve_approver_identity() -> tuple[str, list[str]]:
    """Identity used when approving/rejecting an interrupted action."""
    user_id, roles = resolve_chainlit_identity()
    if user_id == "anonymous" and os.getenv("ONTOLOGY_APPROVER_ROLES"):
        roles = _parse_roles(os.getenv("ONTOLOGY_APPROVER_ROLES", "admin"))
    return user_id, roles
