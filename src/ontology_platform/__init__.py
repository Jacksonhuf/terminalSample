"""Ontology-based agent platform."""

from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.service import OntologyService
from ontology_platform.platform import AgentPlatform

__all__ = ["AgentPlatform", "OntologyRegistry", "OntologyService"]
__version__ = "0.1.0"
