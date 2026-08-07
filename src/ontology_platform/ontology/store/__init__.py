"""Ontology persistence backends."""

from ontology_platform.ontology.store.memory import MemoryStore
from ontology_platform.ontology.store.sqlite import SQLiteStore

# Backward-compatible alias
OntologyStore = MemoryStore

__all__ = ["MemoryStore", "OntologyStore", "SQLiteStore"]
