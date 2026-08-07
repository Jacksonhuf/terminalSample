"""Notification service — send now and schedule reminders."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ontology_platform.governance.context import ExecutionContext
from ontology_platform.integrations.channels.chat_cli import ChatCliAdapter
from ontology_platform.integrations.channels.email import EmailAdapter, EmailConfig
from ontology_platform.integrations.message_log import MessageLogStore
from ontology_platform.integrations.outreach.store import OutreachStore
from ontology_platform.integrations.policy import OutboundPolicy
from ontology_platform.integrations.schema import ChannelType, DeliveryResult, OutboundMessage
from ontology_platform.integrations.templates import TemplateRenderer
from ontology_platform.ontology.service import OntologyService


class NotificationService:
    """Orchestrate outbound chat/email with templates, policy, and logging."""

    def __init__(
        self,
        *,
        chat_adapter: ChatCliAdapter | None = None,
        email_adapter: EmailAdapter | None = None,
        message_log: MessageLogStore | None = None,
        outreach_store: OutreachStore | None = None,
        template_renderer: TemplateRenderer | None = None,
        policy: OutboundPolicy | None = None,
        execution_context: ExecutionContext | None = None,
    ) -> None:
        self.chat_adapter = chat_adapter or ChatCliAdapter()
        self.email_adapter = email_adapter or EmailAdapter(EmailConfig(mode="mock"))
        self.message_log = message_log or MessageLogStore()
        self.outreach_store = outreach_store or OutreachStore()
        self.templates = template_renderer or TemplateRenderer()
        self.policy = policy or OutboundPolicy()
        self.execution_context = execution_context or ExecutionContext()

    def set_execution_context(self, ctx: ExecutionContext) -> None:
        self.execution_context = ctx

    def send_now(
        self,
        *,
        channel: ChannelType | str,
        template_id: str,
        person_ids: list[str],
        context: dict[str, Any],
        service: OntologyService,
        object_type: str = "",
        object_id: str = "",
        correlation_id: str = "",
    ) -> DeliveryResult:
        channel_enum = ChannelType(channel) if isinstance(channel, str) else channel
        allowed, deny_msg = self.policy.can_send(self.execution_context, channel_enum)
        if not allowed:
            self.message_log.append(
                channel=channel_enum.value,
                template_id=template_id,
                recipients=person_ids,
                subject="",
                body="",
                status="denied",
                error=deny_msg,
                object_type=object_type,
                object_id=object_id,
                correlation_id=correlation_id,
                created_by=self.execution_context.user_id,
            )
            return DeliveryResult(success=False, channel=channel_enum, error=deny_msg)

        recipients, resolve_err = self.policy.resolve_recipients(
            service, person_ids, channel=channel_enum
        )
        if resolve_err:
            self.message_log.append(
                channel=channel_enum.value,
                template_id=template_id,
                recipients=person_ids,
                subject="",
                body="",
                status="denied",
                error=resolve_err,
                object_type=object_type,
                object_id=object_id,
                correlation_id=correlation_id,
                created_by=self.execution_context.user_id,
            )
            return DeliveryResult(success=False, channel=channel_enum, error=resolve_err)

        subject, body = self.templates.render(
            template_id, context, channel=channel_enum.value
        )
        message = OutboundMessage(
            channel=channel_enum,
            recipients=recipients,
            subject=subject,
            body=body,
            template_id=template_id,
            context=context,
            correlation_id=correlation_id,
            object_type=object_type,
            object_id=object_id,
        )

        adapter = self.chat_adapter if channel_enum == ChannelType.CHAT else self.email_adapter
        result = adapter.send(message)
        self.message_log.append(
            channel=channel_enum.value,
            template_id=template_id,
            recipients=recipients,
            subject=subject,
            body=body,
            status="sent" if result.success else "failed",
            error=result.error,
            object_type=object_type,
            object_id=object_id,
            correlation_id=correlation_id,
            created_by=self.execution_context.user_id,
        )
        return result

    def schedule_reminder(
        self,
        *,
        channel: ChannelType | str,
        template_id: str,
        person_ids: list[str],
        context: dict[str, Any],
        due_at: str | None = None,
        delay_days: int = 0,
        object_type: str = "",
        object_id: str = "",
        person_id: str = "",
        created_by_action: str = "",
    ) -> str:
        channel_enum = ChannelType(channel) if isinstance(channel, str) else channel
        if due_at is None:
            due = datetime.now(timezone.utc) + timedelta(days=delay_days)
            due_at = due.isoformat()

        task = self.outreach_store.create_task(
            channel=channel_enum,
            template_id=template_id,
            recipients=person_ids,
            due_at=due_at,
            context=context,
            object_type=object_type,
            object_id=object_id,
            person_id=person_id or (person_ids[0] if person_ids else ""),
            created_by_action=created_by_action,
        )
        return task.id

    def cancel_reminders(
        self,
        *,
        object_type: str,
        object_id: str,
        template_id: str | None = None,
    ) -> int:
        return self.outreach_store.cancel_pending(
            object_type=object_type,
            object_id=object_id,
            template_id=template_id,
        )

    def get_message_logs(self, object_type: str = "", object_id: str = "", limit: int = 50):
        return self.message_log.query(
            object_type=object_type or None,
            object_id=object_id or None,
            limit=limit,
        )

    def get_outreach_tasks(self, object_type: str = "", object_id: str = "", status: str | None = None):
        return self.outreach_store.list_tasks(
            object_type=object_type or None,
            object_id=object_id or None,
            status=status,
        )
