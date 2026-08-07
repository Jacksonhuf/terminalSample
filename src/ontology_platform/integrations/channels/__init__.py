"""Outbound channel adapters."""

from ontology_platform.integrations.channels.chat_cli import ChatCliAdapter, ChatCliConfig
from ontology_platform.integrations.channels.email import EmailAdapter, EmailConfig

__all__ = ["ChatCliAdapter", "ChatCliConfig", "EmailAdapter", "EmailConfig"]
