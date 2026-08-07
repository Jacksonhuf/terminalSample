"""Ontology-based agent platform."""

from ontology_platform.agent.config import AgentConfig
from ontology_platform.apps.prototype import PrototypeApp
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.service import OntologyService
from ontology_platform.ontology.store import MemoryStore, OntologyStore, SQLiteStore
from ontology_platform.platform import AgentPlatform, ChatResult

__all__ = [
    "AgentConfig",
    "AgentPlatform",
    "ChatResult",
    "MemoryStore",
    "OntologyRegistry",
    "OntologyService",
    "OntologyStore",
    "PrototypeApp",
    "SQLiteStore",
]
__version__ = "0.1.0"
