"""Create ontology store from agent configuration."""

from __future__ import annotations

from ontology_platform.agent.config import AgentConfig
from ontology_platform.ontology.store.memory import MemoryStore


def create_store(config: AgentConfig | None = None):
    cfg = config or AgentConfig()
    backend = cfg.resolve_store_backend()

    if backend == "postgres":
        from ontology_platform.ontology.store.postgres import PostgreSQLStore

        if not cfg.database_url:
            raise ValueError("database_url is required for postgres store backend")
        return PostgreSQLStore(cfg.database_url)

    if backend == "sqlite":
        from ontology_platform.ontology.store.sqlite import SQLiteStore

        if not cfg.store_path:
            raise ValueError("store_path is required for sqlite store backend")
        return SQLiteStore(cfg.store_path)

    return MemoryStore()


def create_checkpointer(config: AgentConfig | None = None):
    """Return a persistent LangGraph checkpointer when configured."""
    cfg = config or AgentConfig()
    checkpoint_path = cfg.get_checkpoint_path()
    if checkpoint_path is None:
        return None
    try:
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        return None
    conn = sqlite3.connect(checkpoint_path, check_same_thread=False)
    return SqliteSaver(conn)
