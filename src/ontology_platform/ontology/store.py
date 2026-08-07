"""In-memory ontology object store."""

from __future__ import annotations

from ontology_platform.ontology.schema import LinkInstance, OntologyObject


class OntologyStore:
    """Simple in-memory store for ontology objects and links."""

    def __init__(self) -> None:
        self._objects: dict[str, dict[str, OntologyObject]] = {}
        self._links: list[LinkInstance] = []

    def create_object(self, obj: OntologyObject) -> OntologyObject:
        bucket = self._objects.setdefault(obj.object_type, {})
        if obj.object_id in bucket:
            raise ValueError(f"Object already exists: {obj.object_type}/{obj.object_id}")
        bucket[obj.object_id] = obj
        return obj

    def get_object(self, object_type: str, object_id: str) -> OntologyObject | None:
        return self._objects.get(object_type, {}).get(object_id)

    def update_object(self, obj: OntologyObject) -> OntologyObject:
        bucket = self._objects.setdefault(obj.object_type, {})
        if obj.object_id not in bucket:
            raise ValueError(f"Object not found: {obj.object_type}/{obj.object_id}")
        bucket[obj.object_id] = obj
        return obj

    def delete_object(self, object_type: str, object_id: str) -> bool:
        bucket = self._objects.get(object_type, {})
        if object_id in bucket:
            del bucket[object_id]
            self._links = [
                link
                for link in self._links
                if not (
                    (link.source_type == object_type and link.source_id == object_id)
                    or (link.target_type == object_type and link.target_id == object_id)
                )
            ]
            return True
        return False

    def list_objects(
        self,
        object_type: str,
        filters: dict | None = None,
        limit: int = 100,
    ) -> list[OntologyObject]:
        objects = list(self._objects.get(object_type, {}).values())
        if filters:
            objects = [
                obj
                for obj in objects
                if all(obj.properties.get(k) == v for k, v in filters.items())
            ]
        return objects[:limit]

    def create_link(self, link: LinkInstance) -> LinkInstance:
        self._links.append(link)
        return link

    def get_links(
        self,
        link_type: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> list[LinkInstance]:
        results = self._links
        if link_type:
            results = [l for l in results if l.link_type == link_type]
        if source_type:
            results = [l for l in results if l.source_type == source_type]
        if source_id:
            results = [l for l in results if l.source_id == source_id]
        if target_type:
            results = [l for l in results if l.target_type == target_type]
        if target_id:
            results = [l for l in results if l.target_id == target_id]
        return results

    def delete_links(
        self,
        link_type: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> int:
        to_remove = self.get_links(link_type, source_type, source_id, target_type, target_id)
        for link in to_remove:
            self._links.remove(link)
        return len(to_remove)

    def clear(self) -> None:
        self._objects.clear()
        self._links.clear()
