"""Ontology persistence backends."""

from ontology_platform.ontology.store.factory import create_checkpointer, create_store
from ontology_platform.ontology.store.memory import MemoryStore
from ontology_platform.ontology.store.postgres import PostgreSQLStore
from ontology_platform.ontology.store.sqlite import SQLiteStore

# Backward-compatible alias
OntologyStore = MemoryStore

__all__ = [
    "MemoryStore",
    "OntologyStore",
    "PostgreSQLStore",
    "SQLiteStore",
    "create_checkpointer",
    "create_store",
]
