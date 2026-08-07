"""SQLite-backed ontology persistence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ontology_platform.ontology.schema import LinkInstance, OntologyObject


class SQLiteStore:
    """Persist ontology objects and links in SQLite."""

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
                CREATE TABLE IF NOT EXISTS objects (
                    object_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    properties TEXT NOT NULL,
                    PRIMARY KEY (object_type, object_id)
                );
                CREATE TABLE IF NOT EXISTS links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    link_type TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    properties TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_links_source
                    ON links(source_type, source_id);
                CREATE INDEX IF NOT EXISTS idx_links_target
                    ON links(target_type, target_id);
                """
            )

    def create_object(self, obj: OntologyObject) -> OntologyObject:
        if self.get_object(obj.object_type, obj.object_id):
            raise ValueError(f"Object already exists: {obj.object_type}/{obj.object_id}")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO objects (object_type, object_id, properties) VALUES (?, ?, ?)",
                (obj.object_type, obj.object_id, json.dumps(obj.properties, ensure_ascii=False)),
            )
        return obj

    def get_object(self, object_type: str, object_id: str) -> OntologyObject | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM objects WHERE object_type = ? AND object_id = ?",
                (object_type, object_id),
            ).fetchone()
        if row is None:
            return None
        return OntologyObject(
            object_type=row["object_type"],
            object_id=row["object_id"],
            properties=json.loads(row["properties"]),
        )

    def update_object(self, obj: OntologyObject) -> OntologyObject:
        if self.get_object(obj.object_type, obj.object_id) is None:
            raise ValueError(f"Object not found: {obj.object_type}/{obj.object_id}")
        with self._connect() as conn:
            conn.execute(
                "UPDATE objects SET properties = ? WHERE object_type = ? AND object_id = ?",
                (json.dumps(obj.properties, ensure_ascii=False), obj.object_type, obj.object_id),
            )
        return obj

    def delete_object(self, object_type: str, object_id: str) -> bool:
        if self.get_object(object_type, object_id) is None:
            return False
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM objects WHERE object_type = ? AND object_id = ?",
                (object_type, object_id),
            )
            conn.execute(
                """
                DELETE FROM links
                WHERE (source_type = ? AND source_id = ?)
                   OR (target_type = ? AND target_id = ?)
                """,
                (object_type, object_id, object_type, object_id),
            )
        return True

    def list_objects(
        self,
        object_type: str,
        filters: dict | None = None,
        limit: int = 100,
    ) -> list[OntologyObject]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM objects WHERE object_type = ? LIMIT ?",
                (object_type, limit * 10),
            ).fetchall()
        objects = [
            OntologyObject(
                object_type=row["object_type"],
                object_id=row["object_id"],
                properties=json.loads(row["properties"]),
            )
            for row in rows
        ]
        if filters:
            objects = [
                obj
                for obj in objects
                if all(obj.properties.get(k) == v for k, v in filters.items())
            ]
        return objects[:limit]

    def create_link(self, link: LinkInstance) -> LinkInstance:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO links
                    (link_type, source_type, source_id, target_type, target_id, properties)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    link.link_type,
                    link.source_type,
                    link.source_id,
                    link.target_type,
                    link.target_id,
                    json.dumps(link.properties, ensure_ascii=False),
                ),
            )
        return link

    def get_links(
        self,
        link_type: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> list[LinkInstance]:
        query = "SELECT * FROM links WHERE 1=1"
        params: list = []
        if link_type:
            query += " AND link_type = ?"
            params.append(link_type)
        if source_type:
            query += " AND source_type = ?"
            params.append(source_type)
        if source_id:
            query += " AND source_id = ?"
            params.append(source_id)
        if target_type:
            query += " AND target_type = ?"
            params.append(target_type)
        if target_id:
            query += " AND target_id = ?"
            params.append(target_id)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            LinkInstance(
                link_type=row["link_type"],
                source_type=row["source_type"],
                source_id=row["source_id"],
                target_type=row["target_type"],
                target_id=row["target_id"],
                properties=json.loads(row["properties"]),
            )
            for row in rows
        ]

    def delete_links(
        self,
        link_type: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> int:
        links = self.get_links(link_type, source_type, source_id, target_type, target_id)
        if not links:
            return 0
        with self._connect() as conn:
            for link in links:
                conn.execute(
                    """
                    DELETE FROM links
                    WHERE link_type = ? AND source_type = ? AND source_id = ?
                      AND target_type = ? AND target_id = ?
                    """,
                    (
                        link.link_type,
                        link.source_type,
                        link.source_id,
                        link.target_type,
                        link.target_id,
                    ),
                )
        return len(links)

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM links")
            conn.execute("DELETE FROM objects")
