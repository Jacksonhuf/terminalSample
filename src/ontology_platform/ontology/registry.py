"""Ontology definition registry and YAML loader."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import yaml

from ontology_platform.ontology.schema import ActionResult, OntologyDef


ActionHandler = Callable[..., ActionResult]


class OntologyRegistry:
    """Registers ontology definitions and action handlers."""

    def __init__(self) -> None:
        self._ontologies: dict[str, OntologyDef] = {}
        self._action_handlers: dict[str, ActionHandler] = {}

    def register(self, ontology: OntologyDef) -> None:
        self._ontologies[ontology.name] = ontology

    def get(self, name: str) -> OntologyDef | None:
        return self._ontologies.get(name)

    def list_ontologies(self) -> list[str]:
        return list(self._ontologies.keys())

    def register_action_handler(
        self,
        ontology_name: str,
        action_name: str,
        handler: ActionHandler,
    ) -> None:
        key = f"{ontology_name}.{action_name}"
        self._action_handlers[key] = handler

    def get_action_handler(self, ontology_name: str, action_name: str) -> ActionHandler | None:
        return self._action_handlers.get(f"{ontology_name}.{action_name}")

    @classmethod
    def from_yaml(cls, path: str | Path) -> OntologyRegistry:
        registry = cls()
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        ontology = OntologyDef.model_validate(data)
        registry.register(ontology)
        return registry
