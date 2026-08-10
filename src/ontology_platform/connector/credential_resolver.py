"""Resolve connector credentials for Computer Use runtime."""

from __future__ import annotations

import os
from typing import Any

from ontology_platform.connector.credential_store import CredentialStore
from ontology_platform.connector.schema import ConnectorDef, LoginConfig


def build_login_task_payload(
    connector: ConnectorDef,
    credential_store: CredentialStore | None,
) -> dict[str, Any]:
    """Build login metadata for a Computer Use task (never includes password)."""
    login_cfg = connector.login or LoginConfig()
    payload: dict[str, Any] = {
        "type": login_cfg.type,
        "login_url": login_cfg.login_url or connector.source_url,
        "username_field": login_cfg.username_field,
        "password_field": login_cfg.password_field,
        "post_login_wait": login_cfg.post_login_wait,
        "username": "",
        "password_provided": False,
        "credential_ref": connector.credential_ref or "",
    }

    if not connector.credential_ref or credential_store is None:
        return payload

    secret = credential_store.get_secret(connector.credential_ref)
    if secret is None:
        return payload

    credential_store.mark_used(connector.credential_ref)
    payload["username"] = secret.username
    payload["password_provided"] = True
    if secret.login_url:
        payload["login_url"] = secret.login_url
    elif login_cfg.login_url:
        payload["login_url"] = login_cfg.login_url
    return payload


def inject_credentials_env(
    connector: ConnectorDef,
    credential_store: CredentialStore | None,
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Inject CU_USERNAME / CU_PASSWORD into environment for subprocess runners."""
    result = dict(env or os.environ)
    if not connector.credential_ref or credential_store is None:
        return result

    secret = credential_store.get_secret(connector.credential_ref)
    if secret is None:
        return result

    credential_store.mark_used(connector.credential_ref)
    result["CU_USERNAME"] = secret.username
    result["CU_PASSWORD"] = secret.password
    result["CU_CREDENTIAL_REF"] = connector.credential_ref
    login_url = (connector.login.login_url if connector.login else "") or secret.login_url
    if login_url:
        result["CU_LOGIN_URL"] = login_url
    return result
