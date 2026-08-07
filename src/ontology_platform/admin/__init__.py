"""Ontology admin web interface."""

from ontology_platform.admin.manager import OntologyManager
from ontology_platform.admin.server import create_app

__all__ = ["OntologyManager", "create_app"]
