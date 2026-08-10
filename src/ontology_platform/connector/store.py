"""SQL storage for connector raw captures and ingestion runs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ontology_platform.connector.schema import IngestionRun, StagedRecord


class ConnectorStore:
    """Persist Computer Use captures and sync state in SQLite."""

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
                CREATE TABLE IF NOT EXISTS connector_runs (
                    id TEXT PRIMARY KEY,
                    connector_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    source_url TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    records_captured INTEGER DEFAULT 0,
                    records_synced INTEGER DEFAULT 0,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS connector_staged_records (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    connector_name TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    synced INTEGER DEFAULT 0,
                    ontology_object_id TEXT,
                    captured_at TEXT NOT NULL,
                    UNIQUE(run_id, record_type, external_id)
                );
                CREATE INDEX IF NOT EXISTS idx_staged_connector
                    ON connector_staged_records(connector_name, synced);
                CREATE INDEX IF NOT EXISTS idx_staged_run ON connector_staged_records(run_id);
                """
            )

    def create_run(self, connector_name: str, mode: str, source_url: str = "") -> IngestionRun:
        run = IngestionRun(
            id=str(uuid.uuid4()),
            connector_name=connector_name,
            status="running",
            mode=mode,
            source_url=source_url,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO connector_runs
                    (id, connector_name, status, mode, source_url, started_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run.id, run.connector_name, run.status, run.mode, run.source_url, run.started_at),
            )
        return run

    def complete_run(
        self,
        run_id: str,
        *,
        status: str = "completed",
        records_captured: int = 0,
        records_synced: int = 0,
        error: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE connector_runs
                SET status=?, finished_at=?, records_captured=?, records_synced=?, error=?
                WHERE id=?
                """,
                (
                    status,
                    datetime.now(timezone.utc).isoformat(),
                    records_captured,
                    records_synced,
                    error,
                    run_id,
                ),
            )

    def stage_record(
        self,
        run_id: str,
        connector_name: str,
        record_type: str,
        external_id: str,
        payload: dict[str, Any],
    ) -> StagedRecord:
        record = StagedRecord(
            id=str(uuid.uuid4()),
            run_id=run_id,
            connector_name=connector_name,
            record_type=record_type,
            external_id=external_id,
            payload=payload,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO connector_staged_records
                    (id, run_id, connector_name, record_type, external_id, payload, synced, captured_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    record.id,
                    record.run_id,
                    record.connector_name,
                    record.record_type,
                    record.external_id,
                    json.dumps(payload, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return record

    def list_unsynced(self, connector_name: str | None = None, limit: int = 500) -> list[StagedRecord]:
        return self.list_staged_records(connector_name=connector_name, synced=False, limit=limit)

    def list_staged_records(
        self,
        connector_name: str | None = None,
        record_type: str | None = None,
        *,
        synced: bool | None = None,
        run_id: str | None = None,
        limit: int = 500,
    ) -> list[StagedRecord]:
        query = "SELECT * FROM connector_staged_records WHERE 1=1"
        params: list = []
        if connector_name:
            query += " AND connector_name=?"
            params.append(connector_name)
        if record_type:
            query += " AND record_type=?"
            params.append(record_type)
        if synced is not None:
            query += " AND synced=?"
            params.append(int(synced))
        if run_id:
            query += " AND run_id=?"
            params.append(run_id)
        query += " ORDER BY captured_at LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_staged(r) for r in rows]

    def summarize_staged(self, connector_name: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT connector_name, record_type,
                   COUNT(*) AS total,
                   SUM(CASE WHEN synced=0 THEN 1 ELSE 0 END) AS unsynced,
                   SUM(CASE WHEN synced=1 THEN 1 ELSE 0 END) AS synced
            FROM connector_staged_records
        """
        params: list = []
        if connector_name:
            query += " WHERE connector_name=?"
            params.append(connector_name)
        query += " GROUP BY connector_name, record_type ORDER BY connector_name, record_type"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "connector_name": r["connector_name"],
                "record_type": r["record_type"],
                "total": r["total"],
                "unsynced": r["unsynced"],
                "synced": r["synced"],
            }
            for r in rows
        ]

    def infer_fields(self, connector_name: str, record_type: str, limit: int = 20) -> list[str]:
        records = self.list_staged_records(
            connector_name=connector_name,
            record_type=record_type,
            limit=limit,
        )
        fields: list[str] = []
        seen: set[str] = set()
        for record in records:
            for key in record.payload:
                if key not in seen:
                    seen.add(key)
                    fields.append(key)
        return fields

    def reset_synced(self, connector_name: str, record_type: str | None = None) -> int:
        query = "UPDATE connector_staged_records SET synced=0, ontology_object_id=NULL WHERE connector_name=?"
        params: list = [connector_name]
        if record_type:
            query += " AND record_type=?"
            params.append(record_type)
        with self._connect() as conn:
            cur = conn.execute(query, params)
        return cur.rowcount

    def mark_synced(self, record_id: str, ontology_object_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE connector_staged_records
                SET synced=1, ontology_object_id=?
                WHERE id=?
                """,
                (ontology_object_id, record_id),
            )

    def get_run(self, run_id: str) -> IngestionRun | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM connector_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        return IngestionRun(
            id=row["id"],
            connector_name=row["connector_name"],
            status=row["status"],
            mode=row["mode"],
            source_url=row["source_url"] or "",
            started_at=row["started_at"],
            finished_at=row["finished_at"] or "",
            records_captured=row["records_captured"],
            records_synced=row["records_synced"],
            error=row["error"] or "",
        )

    def list_runs(self, connector_name: str | None = None, limit: int = 50) -> list[IngestionRun]:
        query = "SELECT * FROM connector_runs"
        params: list = []
        if connector_name:
            query += " WHERE connector_name=?"
            params.append(connector_name)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            IngestionRun(
                id=r["id"],
                connector_name=r["connector_name"],
                status=r["status"],
                mode=r["mode"],
                source_url=r["source_url"] or "",
                started_at=r["started_at"],
                finished_at=r["finished_at"] or "",
                records_captured=r["records_captured"],
                records_synced=r["records_synced"],
                error=r["error"] or "",
            )
            for r in rows
        ]

    def _row_to_staged(self, row: sqlite3.Row) -> StagedRecord:
        return StagedRecord(
            id=row["id"],
            run_id=row["run_id"],
            connector_name=row["connector_name"],
            record_type=row["record_type"],
            external_id=row["external_id"],
            payload=json.loads(row["payload"]),
            synced=bool(row["synced"]),
            ontology_object_id=row["ontology_object_id"] or "",
        )
