"""Load LLM model and planner settings from persistent configuration."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from ontology_platform.agent.config import AgentConfig
from ontology_platform.connector.credential_store import CredentialStore
from ontology_platform.llm.factory import build_chat_model_from_store
from ontology_platform.llm.schema import LlmProfile
from ontology_platform.llm.store import LlmConfigStore


def load_llm_runtime(
    config: AgentConfig,
    *,
    profile_id: str | None = None,
    apply_planner_mode: bool = True,
) -> tuple[BaseChatModel | None, LlmProfile | None]:
    """Load default (or specified) LLM profile from config.store_path."""
    if not config.store_path:
        return None, None

    llm_store = LlmConfigStore(config.store_path)
    credential_store = CredentialStore(config.store_path)
    profile = (
        llm_store.get_profile(profile_id)
        if profile_id
        else llm_store.get_default_profile()
    )
    if profile is None or not profile.enabled:
        return None, None

    model = build_chat_model_from_store(llm_store, credential_store, profile_id=profile.id)
    if model is not None and apply_planner_mode and profile.planner_mode:
        config.planner_mode = profile.planner_mode
    return model, profile
