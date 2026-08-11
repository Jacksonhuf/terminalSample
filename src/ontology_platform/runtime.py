"""Build runtime AgentPlatform instances for admin/API use."""

from __future__ import annotations

from pathlib import Path

from ontology_platform.agent.config import AgentConfig
from ontology_platform.llm.loader import load_llm_runtime
from ontology_platform.platform import AgentPlatform


def build_runtime_platform(
    *,
    ontology_yaml: str | Path,
    store_path: str | Path | None = None,
    database_url: str | None = None,
    store_backend: str = "auto",
    audit_path: str | Path | None = None,
    integrations_db_path: str | Path | None = None,
) -> AgentPlatform:
    config = AgentConfig(
        store_path=str(store_path) if store_path else None,
        database_url=database_url,
        store_backend=store_backend,  # type: ignore[arg-type]
        audit_path=str(audit_path) if audit_path else None,
        integrations_db_path=str(integrations_db_path) if integrations_db_path else None,
        enable_governance=True,
        enable_approval_flow=True,
    )
    model, _ = load_llm_runtime(config)
    return AgentPlatform.from_yaml(ontology_yaml, config=config, model=model)
