"""Ontology YAML file management."""

from __future__ import annotations

from pathlib import Path

import yaml

from ontology_platform.ontology.schema import OntologyDef


class OntologyManager:
    """Manage ontology definitions stored as YAML files."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def list_ontologies(self) -> list[dict]:
        results = []
        for path in sorted(self.directory.glob("*.yaml")):
            ontology = self._load_file(path)
            results.append(
                {
                    "name": ontology.name,
                    "filename": path.name,
                    "version": ontology.version,
                    "description": ontology.description,
                    "object_type_count": len(ontology.object_types),
                    "link_count": len(ontology.links),
                    "action_count": len(ontology.actions),
                }
            )
        return results

    def load(self, name: str) -> OntologyDef:
        path = self._path_for(name)
        if path.exists():
            return self._load_file(path)
        for yaml_path in self.directory.glob("*.yaml"):
            ontology = self._load_file(yaml_path)
            if ontology.name == name:
                return ontology
        raise FileNotFoundError(f"Ontology not found: {name}")

    def _load_file(self, path: Path) -> OntologyDef:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return OntologyDef.model_validate(data)

    def save(self, ontology: OntologyDef) -> Path:
        path = self._path_for(ontology.name)
        data = ontology.model_dump(mode="json", exclude_none=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return path

    def delete(self, name: str) -> bool:
        path = self._path_for(name)
        if path.exists():
            path.unlink()
            return True
        for yaml_path in self.directory.glob("*.yaml"):
            if self._load_file(yaml_path).name == name:
                yaml_path.unlink()
                return True
        return False

    def create(self, ontology: OntologyDef) -> Path:
        path = self._path_for(ontology.name)
        if path.exists():
            raise ValueError(f"Ontology already exists: {ontology.name}")
        return self.save(ontology)

    def to_graph(self, name: str) -> dict:
        """Export ontology as graph nodes/edges for visualization."""
        ontology = self.load(name)
        nodes = []
        for obj_type in ontology.object_types:
            nodes.append(
                {
                    "id": obj_type.name,
                    "label": obj_type.display_name or obj_type.name,
                    "type": "object_type",
                    "group": "object_type",
                    "title": obj_type.description or obj_type.name,
                    "property_count": len(obj_type.properties),
                }
            )

        edges = []
        for link in ontology.links:
            edges.append(
                {
                    "id": link.name,
                    "from": link.source_type,
                    "to": link.target_type,
                    "label": link.name,
                    "arrows": "to",
                    "title": link.description or f"{link.source_type} → {link.target_type}",
                }
            )

        for action in ontology.actions:
            action_node_id = f"action:{action.name}"
            nodes.append(
                {
                    "id": action_node_id,
                    "label": action.display_name or action.name,
                    "type": "action",
                    "group": "action",
                    "title": action.description or action.name,
                    "requires_approval": action.requires_approval,
                }
            )
            edges.append(
                {
                    "id": f"edge:{action.name}",
                    "from": action_node_id,
                    "to": action.target_type,
                    "label": "acts on",
                    "dashes": True,
                    "arrows": "to",
                }
            )

        return {
            "ontology": ontology.name,
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "object_types": len(ontology.object_types),
                "links": len(ontology.links),
                "actions": len(ontology.actions),
            },
        }

    def _path_for(self, name: str) -> Path:
        return self.directory / f"{name}.yaml"
