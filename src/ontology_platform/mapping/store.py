"""SQLite persistence for mapping profiles and sync logs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ontology_platform.mapping.schema import FieldRule, MappingProfile, SyncRunLog, ValueTransform


class MappingStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
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
                CREATE TABLE IF NOT EXISTS mapping_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    connector_name TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    ontology_name TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    id_field TEXT NOT NULL DEFAULT 'id',
                    source_id_field TEXT NOT NULL DEFAULT 'id',
                    field_rules_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_mapping_connector_record
                    ON mapping_profiles(connector_name, record_type);
                CREATE TABLE IF NOT EXISTS mapping_sync_runs (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    connector_name TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    records_processed INTEGER DEFAULT 0,
                    records_synced INTEGER DEFAULT 0,
                    records_failed INTEGER DEFAULT 0,
                    errors_json TEXT NOT NULL DEFAULT '[]',
                    resync INTEGER DEFAULT 0
                );
                """
            )

    def list_profiles(
        self,
        connector_name: str | None = None,
        record_type: str | None = None,
        status: str | None = None,
    ) -> list[MappingProfile]:
        query = "SELECT * FROM mapping_profiles WHERE 1=1"
        params: list = []
        if connector_name:
            query += " AND connector_name=?"
            params.append(connector_name)
        if record_type:
            query += " AND record_type=?"
            params.append(record_type)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_profile(r) for r in rows]

    def get_profile(self, profile_id: str) -> MappingProfile | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mapping_profiles WHERE id=?",
                (profile_id,),
            ).fetchone()
        return self._row_to_profile(row) if row else None

    def get_active_profile(self, connector_name: str, record_type: str) -> MappingProfile | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM mapping_profiles
                WHERE connector_name=? AND record_type=? AND status='active'
                ORDER BY updated_at DESC LIMIT 1
                """,
                (connector_name, record_type),
            ).fetchone()
        return self._row_to_profile(row) if row else None

    def create_profile(
        self,
        *,
        name: str,
        connector_name: str,
        record_type: str,
        ontology_name: str,
        object_type: str,
        id_field: str = "id",
        source_id_field: str = "id",
        field_rules: list[FieldRule] | None = None,
        status: str = "draft",
        profile_id: str | None = None,
    ) -> MappingProfile:
        now = datetime.now(timezone.utc).isoformat()
        profile = MappingProfile(
            id=profile_id or str(uuid.uuid4()),
            name=name,
            connector_name=connector_name,
            record_type=record_type,
            ontology_name=ontology_name,
            object_type=object_type,
            id_field=id_field,
            source_id_field=source_id_field,
            field_rules=field_rules or [],
            status=status,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mapping_profiles
                    (id, name, connector_name, record_type, ontology_name, object_type,
                     id_field, source_id_field, field_rules_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.id,
                    profile.name,
                    profile.connector_name,
                    profile.record_type,
                    profile.ontology_name,
                    profile.object_type,
                    profile.id_field,
                    profile.source_id_field,
                    json.dumps([r.model_dump() for r in profile.field_rules], ensure_ascii=False),
                    profile.status,
                    profile.created_at,
                    profile.updated_at,
                ),
            )
        return profile

    def update_profile(self, profile: MappingProfile) -> MappingProfile:
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE mapping_profiles
                SET name=?, connector_name=?, record_type=?, ontology_name=?, object_type=?,
                    id_field=?, source_id_field=?, field_rules_json=?, status=?, updated_at=?
                WHERE id=?
                """,
                (
                    profile.name,
                    profile.connector_name,
                    profile.record_type,
                    profile.ontology_name,
                    profile.object_type,
                    profile.id_field,
                    profile.source_id_field,
                    json.dumps([r.model_dump() for r in profile.field_rules], ensure_ascii=False),
                    profile.status,
                    profile.updated_at,
                    profile.id,
                ),
            )
        return profile

    def delete_profile(self, profile_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM mapping_profiles WHERE id=?", (profile_id,))
        return cur.rowcount > 0

    def activate_profile(self, profile_id: str) -> MappingProfile:
        profile = self.get_profile(profile_id)
        if profile is None:
            raise ValueError(f"Mapping profile not found: {profile_id}")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE mapping_profiles SET status='archived', updated_at=?
                WHERE connector_name=? AND record_type=? AND status='active' AND id<>?
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    profile.connector_name,
                    profile.record_type,
                    profile_id,
                ),
            )
        profile.status = "active"
        return self.update_profile(profile)

    def create_sync_run(self, profile: MappingProfile, *, resync: bool = False) -> SyncRunLog:
        run = SyncRunLog(
            id=str(uuid.uuid4()),
            profile_id=profile.id,
            connector_name=profile.connector_name,
            record_type=profile.record_type,
            started_at=datetime.now(timezone.utc).isoformat(),
            resync=resync,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mapping_sync_runs
                    (id, profile_id, connector_name, record_type, started_at, status, resync)
                VALUES (?, ?, ?, ?, ?, 'running', ?)
                """,
                (
                    run.id,
                    run.profile_id,
                    run.connector_name,
                    run.record_type,
                    run.started_at,
                    int(resync),
                ),
            )
        return run

    def complete_sync_run(self, run: SyncRunLog) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE mapping_sync_runs
                SET finished_at=?, status=?, records_processed=?, records_synced=?,
                    records_failed=?, errors_json=?
                WHERE id=?
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    run.status,
                    run.records_processed,
                    run.records_synced,
                    run.records_failed,
                    json.dumps(run.errors, ensure_ascii=False),
                    run.id,
                ),
            )

    def list_sync_runs(self, profile_id: str | None = None, limit: int = 50) -> list[SyncRunLog]:
        query = "SELECT * FROM mapping_sync_runs"
        params: list = []
        if profile_id:
            query += " WHERE profile_id=?"
            params.append(profile_id)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_sync_run(r) for r in rows]

    def _row_to_profile(self, row: sqlite3.Row) -> MappingProfile:
        rules_data = json.loads(row["field_rules_json"] or "[]")
        field_rules = []
        for item in rules_data:
            transform = ValueTransform(**item.get("transform", {}))
            field_rules.append(FieldRule(source=item["source"], target=item["target"], transform=transform))
        return MappingProfile(
            id=row["id"],
            name=row["name"],
            connector_name=row["connector_name"],
            record_type=row["record_type"],
            ontology_name=row["ontology_name"],
            object_type=row["object_type"],
            id_field=row["id_field"],
            source_id_field=row["source_id_field"],
            field_rules=field_rules,
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_sync_run(self, row: sqlite3.Row) -> SyncRunLog:
        return SyncRunLog(
            id=row["id"],
            profile_id=row["profile_id"],
            connector_name=row["connector_name"],
            record_type=row["record_type"],
            started_at=row["started_at"],
            finished_at=row["finished_at"] or "",
            status=row["status"],
            records_processed=row["records_processed"],
            records_synced=row["records_synced"],
            records_failed=row["records_failed"],
            errors=json.loads(row["errors_json"] or "[]"),
            resync=bool(row["resync"]),
        )
