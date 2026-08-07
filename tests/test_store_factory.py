"""Tests for store factory and PostgreSQL backend selection."""

from ontology_platform.agent.config import AgentConfig
from ontology_platform.ontology.store.factory import create_store
from ontology_platform.ontology.store.memory import MemoryStore
from ontology_platform.ontology.store.sqlite import SQLiteStore


def test_create_memory_store():
    config = AgentConfig(store_backend="memory")
    store = create_store(config)
    assert isinstance(store, MemoryStore)


def test_create_sqlite_store(tmp_path):
    config = AgentConfig(store_path=str(tmp_path / "data.db"))
    store = create_store(config)
    assert isinstance(store, SQLiteStore)


def test_resolve_postgres_backend():
    config = AgentConfig(database_url="postgresql://user:pass@localhost/test")
    assert config.resolve_store_backend() == "postgres"


def test_checkpoint_path_default(tmp_path):
    config = AgentConfig(store_path=str(tmp_path / "platform.db"))
    assert config.get_checkpoint_path().endswith("platform.checkpoints.db")
