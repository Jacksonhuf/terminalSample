"""PostgreSQL-backed ontology persistence."""

from __future__ import annotations

import json
from typing import Any

from ontology_platform.ontology.schema import LinkInstance, OntologyObject

_SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    properties JSONB NOT NULL,
    PRIMARY KEY (object_type, object_id)
);
CREATE TABLE IF NOT EXISTS links (
    id SERIAL PRIMARY KEY,
    link_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_links_target ON links(target_type, target_id);
"""


class PostgreSQLStore:
    """Persist ontology objects and links in PostgreSQL."""

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as exc:
            raise ImportError(
                "Install PostgreSQL support: pip install -e '.[postgres]'"
            ) from exc
        self.database_url = database_url
        self._psycopg = psycopg
        self._init_db()

    def _connect(self):
        return self._psycopg.connect(self.database_url)

    def _init_db(self) -> None:
        with self._connect() as conn:
            for statement in _SCHEMA.split(";"):
                sql = statement.strip()
                if sql:
                    conn.execute(sql)
            conn.commit()

    def create_object(self, obj: OntologyObject) -> OntologyObject:
        if self.get_object(obj.object_type, obj.object_id):
            raise ValueError(f"Object already exists: {obj.object_type}/{obj.object_id}")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO objects (object_type, object_id, properties) VALUES (%s, %s, %s)",
                (obj.object_type, obj.object_id, json.dumps(obj.properties, ensure_ascii=False)),
            )
            conn.commit()
        return obj

    def get_object(self, object_type: str, object_id: str) -> OntologyObject | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT object_type, object_id, properties FROM objects WHERE object_type = %s AND object_id = %s",
                (object_type, object_id),
            ).fetchone()
        if row is None:
            return None
        return OntologyObject(
            object_type=row[0],
            object_id=row[1],
            properties=self._load_json(row[2]),
        )

    def update_object(self, obj: OntologyObject) -> OntologyObject:
        if self.get_object(obj.object_type, obj.object_id) is None:
            raise ValueError(f"Object not found: {obj.object_type}/{obj.object_id}")
        with self._connect() as conn:
            conn.execute(
                "UPDATE objects SET properties = %s WHERE object_type = %s AND object_id = %s",
                (json.dumps(obj.properties, ensure_ascii=False), obj.object_type, obj.object_id),
            )
            conn.commit()
        return obj

    def delete_object(self, object_type: str, object_id: str) -> bool:
        if self.get_object(object_type, object_id) is None:
            return False
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM objects WHERE object_type = %s AND object_id = %s",
                (object_type, object_id),
            )
            conn.execute(
                """
                DELETE FROM links
                WHERE (source_type = %s AND source_id = %s)
                   OR (target_type = %s AND target_id = %s)
                """,
                (object_type, object_id, object_type, object_id),
            )
            conn.commit()
        return True

    def list_objects(
        self,
        object_type: str,
        filters: dict | None = None,
        limit: int = 100,
    ) -> list[OntologyObject]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT object_type, object_id, properties FROM objects WHERE object_type = %s LIMIT %s",
                (object_type, limit * 10),
            ).fetchall()
        objects = [
            OntologyObject(
                object_type=row[0],
                object_id=row[1],
                properties=self._load_json(row[2]),
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
                VALUES (%s, %s, %s, %s, %s, %s)
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
            conn.commit()
        return link

    def get_links(
        self,
        link_type: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> list[LinkInstance]:
        query = "SELECT link_type, source_type, source_id, target_type, target_id, properties FROM links WHERE 1=1"
        params: list[Any] = []
        if link_type:
            query += " AND link_type = %s"
            params.append(link_type)
        if source_type:
            query += " AND source_type = %s"
            params.append(source_type)
        if source_id:
            query += " AND source_id = %s"
            params.append(source_id)
        if target_type:
            query += " AND target_type = %s"
            params.append(target_type)
        if target_id:
            query += " AND target_id = %s"
            params.append(target_id)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            LinkInstance(
                link_type=row[0],
                source_type=row[1],
                source_id=row[2],
                target_type=row[3],
                target_id=row[4],
                properties=self._load_json(row[5]),
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
                    WHERE link_type = %s AND source_type = %s AND source_id = %s
                      AND target_type = %s AND target_id = %s
                    """,
                    (
                        link.link_type,
                        link.source_type,
                        link.source_id,
                        link.target_type,
                        link.target_id,
                    ),
                )
            conn.commit()
        return len(links)

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM links")
            conn.execute("DELETE FROM objects")
            conn.commit()

    @staticmethod
    def _load_json(value: Any) -> dict:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return json.loads(value)
        return dict(value)
