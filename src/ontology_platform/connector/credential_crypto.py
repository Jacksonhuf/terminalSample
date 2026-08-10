"""Encrypt/decrypt connector credentials at rest."""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def get_secret_key() -> str:
    return os.environ.get("ONTOLOGY_SECRET_KEY", "dev-only-change-me-in-production")


def _fernet(secret: str | None = None) -> Fernet:
    key_material = hashlib.sha256((secret or get_secret_key()).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


def encrypt_secret(plaintext: str, *, secret: str | None = None) -> str:
    return _fernet(secret).encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str, *, secret: str | None = None) -> str:
    try:
        return _fernet(secret).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt credential (wrong ONTOLOGY_SECRET_KEY?)") from exc
