"""Factory for notification service from agent config and environment."""

from __future__ import annotations

import os
from pathlib import Path

from ontology_platform.agent.config import AgentConfig
from ontology_platform.integrations.channels.chat_cli import ChatCliAdapter, ChatCliConfig
from ontology_platform.integrations.channels.email import EmailAdapter, EmailConfig
from ontology_platform.integrations.message_log import MessageLogStore
from ontology_platform.integrations.notification import NotificationService
from ontology_platform.integrations.outreach.store import OutreachStore
from ontology_platform.integrations.policy import OutboundPolicy


def build_notification_service(config: AgentConfig | None = None) -> NotificationService:
    cfg = config or AgentConfig()
    db_base = cfg.integrations_db_path or cfg.store_path
    message_log = MessageLogStore(db_base)
    outreach_store = OutreachStore(db_base)

    chat_config = ChatCliConfig(
        command=os.getenv("ONTOLOGY_CHAT_CLI", "im-cli"),
        send_template=os.getenv(
            "ONTOLOGY_CHAT_SEND_TEMPLATE",
            "send --user {recipient} --text {body}",
        ),
        group_send_template=os.getenv(
            "ONTOLOGY_CHAT_GROUP_TEMPLATE",
            "send --group {recipient} --text {body}",
        ),
    )
    email_mode = os.getenv("ONTOLOGY_EMAIL_MODE", "mock")
    email_config = EmailConfig(
        mode=email_mode,
        smtp_host=os.getenv("ONTOLOGY_SMTP_HOST", "localhost"),
        smtp_port=int(os.getenv("ONTOLOGY_SMTP_PORT", "25")),
        smtp_user=os.getenv("ONTOLOGY_SMTP_USER", ""),
        smtp_password=os.getenv("ONTOLOGY_SMTP_PASSWORD", ""),
        from_address=os.getenv("ONTOLOGY_EMAIL_FROM", "ontology-platform@local"),
        cli_command=os.getenv("ONTOLOGY_MAIL_CLI", "mail-cli"),
        cli_send_template=os.getenv(
            "ONTOLOGY_MAIL_SEND_TEMPLATE",
            "send --to {recipient} --subject {subject} --body {body}",
        ),
    )

    return NotificationService(
        chat_adapter=ChatCliAdapter(chat_config),
        email_adapter=EmailAdapter(email_config),
        message_log=message_log,
        outreach_store=outreach_store,
        policy=OutboundPolicy(),
    )
