"""Persist LLM profiles and proxy settings."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ontology_platform.connector.credential_store import CredentialStore
from ontology_platform.llm.schema import LlmProfile, LlmProfilePublic, ProxyConfig


class LlmConfigStore:
    """Store LLM model profiles and global proxy configuration."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._profiles: dict[str, dict] = {}
        self._proxy: dict = ProxyConfig().model_dump()
        self.db_path = str(db_path) if db_path else None
        if self.db_path:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._init_db()
            self._load_proxy()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS llm_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    is_default INTEGER NOT NULL,
                    base_url TEXT,
                    model TEXT,
                    api_key_ref TEXT,
                    planner_mode TEXT,
                    proxy_mode TEXT,
                    temperature REAL,
                    timeout_sec INTEGER,
                    max_tokens INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS llm_proxy_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    config TEXT NOT NULL
                );
                """
            )

    def _load_proxy(self) -> None:
        if not self.db_path:
            return
        with self._connect() as conn:
            row = conn.execute("SELECT config FROM llm_proxy_settings WHERE id = 1").fetchone()
        if row:
            self._proxy = json.loads(row["config"])

    def get_proxy_config(self) -> ProxyConfig:
        return ProxyConfig.model_validate(self._proxy)

    def save_proxy_config(self, config: ProxyConfig) -> ProxyConfig:
        self._proxy = config.model_dump()
        if self.db_path:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO llm_proxy_settings (id, config) VALUES (1, ?)",
                    (json.dumps(self._proxy, ensure_ascii=False),),
                )
        return config

    def create_profile(
        self,
        *,
        name: str,
        profile_id: str | None = None,
        provider: str = "openai_compatible",
        base_url: str = "",
        model: str = "",
        api_key_ref: str = "",
        planner_mode: str = "auto",
        proxy_mode: str = "inherit",
        temperature: float = 0.2,
        timeout_sec: int = 60,
        max_tokens: int = 4096,
        enabled: bool = True,
        is_default: bool = False,
    ) -> LlmProfilePublic:
        pid = profile_id or f"llm-{uuid.uuid4().hex[:8]}"
        if self.get_profile(pid) is not None:
            raise ValueError(f"LLM profile already exists: {pid}")
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": pid,
            "name": name,
            "provider": provider,
            "enabled": int(enabled),
            "is_default": int(is_default),
            "base_url": base_url,
            "model": model,
            "api_key_ref": api_key_ref,
            "planner_mode": planner_mode,
            "proxy_mode": proxy_mode,
            "temperature": temperature,
            "timeout_sec": timeout_sec,
            "max_tokens": max_tokens,
            "created_at": now,
            "updated_at": now,
        }
        if is_default:
            self._clear_default()
        self._persist_profile(row)
        return self._to_public(row)

    def update_profile(self, profile_id: str, **fields) -> LlmProfilePublic | None:
        row = self._get_row(profile_id)
        if row is None:
            return None
        for key, value in fields.items():
            if value is None:
                continue
            if key in ("enabled", "is_default"):
                row[key] = int(bool(value))
            else:
                row[key] = value
        if fields.get("is_default"):
            self._clear_default(exclude_id=profile_id)
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._persist_profile(row)
        return self._to_public(row)

    def delete_profile(self, profile_id: str) -> bool:
        if self.get_profile(profile_id) is None:
            return False
        if self.db_path:
            with self._connect() as conn:
                conn.execute("DELETE FROM llm_profiles WHERE id = ?", (profile_id,))
        self._profiles.pop(profile_id, None)
        return True

    def list_profiles(self, credential_store: CredentialStore | None = None) -> list[LlmProfilePublic]:
        if self.db_path:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM llm_profiles ORDER BY name").fetchall()
            return [self._to_public(dict(r), credential_store) for r in rows]
        return [self._to_public(row, credential_store) for row in self._profiles.values()]

    def get_profile(self, profile_id: str) -> LlmProfile | None:
        row = self._get_row(profile_id)
        return self._to_profile(row) if row else None

    def get_default_profile(self) -> LlmProfile | None:
        for profile in self.list_profiles():
            if profile.is_default and profile.enabled:
                return self.get_profile(profile.id)
        for profile in self.list_profiles():
            if profile.enabled:
                return self.get_profile(profile.id)
        return None

    def _clear_default(self, exclude_id: str | None = None) -> None:
        for profile in self.list_profiles():
            if profile.is_default and profile.id != exclude_id:
                self.update_profile(profile.id, is_default=False)

    def _get_row(self, profile_id: str) -> dict | None:
        if self.db_path:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM llm_profiles WHERE id = ?", (profile_id,)).fetchone()
            return dict(row) if row else None
        return self._profiles.get(profile_id)

    def _persist_profile(self, row: dict) -> None:
        self._profiles[row["id"]] = dict(row)
        if self.db_path:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO llm_profiles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        row["id"],
                        row["name"],
                        row["provider"],
                        row["enabled"],
                        row["is_default"],
                        row["base_url"],
                        row["model"],
                        row["api_key_ref"],
                        row["planner_mode"],
                        row["proxy_mode"],
                        row["temperature"],
                        row["timeout_sec"],
                        row["max_tokens"],
                        row["created_at"],
                        row["updated_at"],
                    ),
                )

    def _to_public(self, row: dict, credential_store: CredentialStore | None = None) -> LlmProfilePublic:
        api_key_set = False
        ref = row.get("api_key_ref") or ""
        if ref and credential_store is not None:
            api_key_set = credential_store.get_secret(ref) is not None
        elif ref:
            api_key_set = True
        return LlmProfilePublic(
            id=row["id"],
            name=row["name"],
            provider=row["provider"],
            enabled=bool(row["enabled"]),
            is_default=bool(row["is_default"]),
            base_url=row.get("base_url") or "",
            model=row.get("model") or "",
            api_key_ref=ref,
            api_key_set=api_key_set,
            planner_mode=row.get("planner_mode") or "auto",
            proxy_mode=row.get("proxy_mode") or "inherit",
            temperature=float(row.get("temperature") or 0.2),
            timeout_sec=int(row.get("timeout_sec") or 60),
            max_tokens=int(row.get("max_tokens") or 4096),
            created_at=row.get("created_at") or "",
            updated_at=row.get("updated_at") or "",
        )

    def _to_profile(self, row: dict) -> LlmProfile:
        return LlmProfile(
            id=row["id"],
            name=row["name"],
            provider=row["provider"],
            enabled=bool(row["enabled"]),
            is_default=bool(row["is_default"]),
            base_url=row.get("base_url") or "",
            model=row.get("model") or "",
            api_key_ref=row.get("api_key_ref") or "",
            planner_mode=row.get("planner_mode") or "auto",
            proxy_mode=row.get("proxy_mode") or "inherit",
            temperature=float(row.get("temperature") or 0.2),
            timeout_sec=int(row.get("timeout_sec") or 60),
            max_tokens=int(row.get("max_tokens") or 4096),
            created_at=row.get("created_at") or "",
            updated_at=row.get("updated_at") or "",
        )

    def list_profiles_public(self, credential_store: CredentialStore | None = None) -> list[LlmProfilePublic]:
        return self.list_profiles(credential_store)
