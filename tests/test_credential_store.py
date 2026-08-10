"""Tests for encrypted credential storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from ontology_platform.connector.credential_crypto import decrypt_secret, encrypt_secret
from ontology_platform.connector.credential_store import CredentialStore


def test_encrypt_decrypt_roundtrip() -> None:
    encrypted = encrypt_secret("secret-pass", secret="test-key")
    assert decrypt_secret(encrypted, secret="test-key") == "secret-pass"


def test_credential_store_crud(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds.db")
    cred = store.create(
        name="ERP Prod",
        username="ops_user",
        password="p@ssw0rd",
        credential_id="cred-erp",
        login_url="https://erp.example.com/login",
    )
    assert cred.password_set is True
    assert cred.username == "ops_user"
    assert "password" not in cred.model_dump()

    secret = store.get_secret("cred-erp")
    assert secret is not None
    assert secret.password == "p@ssw0rd"

    updated = store.update("cred-erp", name="ERP Production")
    assert updated is not None
    assert updated.name == "ERP Production"

    rotated = store.rotate_password("cred-erp", "new-pass")
    assert rotated is not None
    assert store.get_secret("cred-erp").password == "new-pass"

    assert store.delete("cred-erp") is True
    assert store.get_public("cred-erp") is None


def test_credential_store_duplicate_id(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds.db")
    store.create(name="A", username="u", password="p", credential_id="cred-1")
    with pytest.raises(ValueError):
        store.create(name="B", username="u2", password="p2", credential_id="cred-1")
