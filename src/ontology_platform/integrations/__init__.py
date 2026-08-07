"""Outbound integrations — chat, email, reminders."""

from ontology_platform.integrations.factory import build_notification_service
from ontology_platform.integrations.notification import NotificationService
from ontology_platform.integrations.outreach.worker import process_due_tasks
from ontology_platform.integrations.schema import ChannelType, DeliveryResult

__all__ = [
    "ChannelType",
    "DeliveryResult",
    "NotificationService",
    "build_notification_service",
    "process_due_tasks",
]
