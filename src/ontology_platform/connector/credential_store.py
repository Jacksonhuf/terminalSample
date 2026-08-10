"""Encrypted credential profiles for Computer Use connectors."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from ontology_platform.connector.credential_crypto import decrypt_secret, encrypt_secret


class CredentialPublic(BaseModel):
    id: str
    name: str
    username: str
    login_url: str = ""
    notes: str = ""
    password_set: bool = True
    created_at: str = ""
    updated_at: str = ""
    last_used_at: str = ""


class CredentialSecret(BaseModel):
    id: str
    username: str
    password: str
    login_url: str = ""


class CredentialStore:
    """Persist connector login credentials separately from YAML definitions."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._memory: dict[str, dict] = {}
        self.db_path = str(db_path) if db_path else None
        if self.db_path:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS credentials (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    password_enc TEXT NOT NULL,
                    login_url TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used_at TEXT
                );
                """
            )

    def create(
        self,
        *,
        name: str,
        username: str,
        password: str,
        credential_id: str | None = None,
        login_url: str = "",
        notes: str = "",
    ) -> CredentialPublic:
        cred_id = credential_id or f"cred-{uuid.uuid4().hex[:8]}"
        if self.get_public(cred_id) is not None:
            raise ValueError(f"Credential already exists: {cred_id}")
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": cred_id,
            "name": name,
            "username": username,
            "password_enc": encrypt_secret(password),
            "login_url": login_url,
            "notes": notes,
            "created_at": now,
            "updated_at": now,
            "last_used_at": "",
        }
        self._persist(row)
        return self._row_to_public(row)

    def update(
        self,
        credential_id: str,
        *,
        name: str | None = None,
        username: str | None = None,
        login_url: str | None = None,
        notes: str | None = None,
    ) -> CredentialPublic | None:
        row = self._get_row(credential_id)
        if row is None:
            return None
        if name is not None:
            row["name"] = name
        if username is not None:
            row["username"] = username
        if login_url is not None:
            row["login_url"] = login_url
        if notes is not None:
            row["notes"] = notes
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._persist(row)
        return self._row_to_public(row)

    def rotate_password(self, credential_id: str, password: str) -> CredentialPublic | None:
        row = self._get_row(credential_id)
        if row is None:
            return None
        row["password_enc"] = encrypt_secret(password)
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._persist(row)
        return self._row_to_public(row)

    def delete(self, credential_id: str) -> bool:
        if self.get_public(credential_id) is None:
            return False
        if self.db_path:
            with self._connect() as conn:
                conn.execute("DELETE FROM credentials WHERE id = ?", (credential_id,))
        self._memory.pop(credential_id, None)
        return True

    def list_public(self) -> list[CredentialPublic]:
        if self.db_path:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM credentials ORDER BY name").fetchall()
            return [self._row_to_public(dict(r)) for r in rows]
        return [self._row_to_public(row) for row in self._memory.values()]

    def get_public(self, credential_id: str) -> CredentialPublic | None:
        row = self._get_row(credential_id)
        return self._row_to_public(row) if row else None

    def get_secret(self, credential_id: str) -> CredentialSecret | None:
        row = self._get_row(credential_id)
        if row is None:
            return None
        return CredentialSecret(
            id=row["id"],
            username=row["username"],
            password=decrypt_secret(row["password_enc"]),
            login_url=row.get("login_url") or "",
        )

    def mark_used(self, credential_id: str) -> None:
        row = self._get_row(credential_id)
        if row is None:
            return
        row["last_used_at"] = datetime.now(timezone.utc).isoformat()
        self._persist(row)

    def _get_row(self, credential_id: str) -> dict | None:
        if self.db_path:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM credentials WHERE id = ?", (credential_id,)
                ).fetchone()
            return dict(row) if row else None
        return self._memory.get(credential_id)

    def _persist(self, row: dict) -> None:
        self._memory[row["id"]] = dict(row)
        if self.db_path:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO credentials
                    (id, name, username, password_enc, login_url, notes,
                     created_at, updated_at, last_used_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        row["name"],
                        row["username"],
                        row["password_enc"],
                        row.get("login_url") or "",
                        row.get("notes") or "",
                        row["created_at"],
                        row["updated_at"],
                        row.get("last_used_at") or "",
                    ),
                )

    def _row_to_public(self, row: dict) -> CredentialPublic:
        return CredentialPublic(
            id=row["id"],
            name=row["name"],
            username=row["username"],
            login_url=row.get("login_url") or "",
            notes=row.get("notes") or "",
            password_set=bool(row.get("password_enc")),
            created_at=row.get("created_at") or "",
            updated_at=row.get("updated_at") or "",
            last_used_at=row.get("last_used_at") or "",
        )
