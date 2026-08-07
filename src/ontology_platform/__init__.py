"""Ontology-based agent platform."""

from ontology_platform.agent.config import AgentConfig
from ontology_platform.apps.prototype import PrototypeApp
from ontology_platform.integrations import NotificationService, build_notification_service
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.service import OntologyService
from ontology_platform.ontology.store import MemoryStore, OntologyStore, SQLiteStore
from ontology_platform.platform import AgentPlatform, ChatResult

__all__ = [
    "AgentConfig",
    "AgentPlatform",
    "AuditLogEntry",
    "AuditLogger",
    "ChatResult",
    "ExecutionContext",
    "MemoryStore",
    "NotificationService",
    "OntologyRegistry",
    "OntologyService",
    "OntologyStore",
    "PolicyEngine",
    "PrototypeApp",
    "SQLiteStore",
    "build_notification_service",
]
__version__ = "0.1.0"
