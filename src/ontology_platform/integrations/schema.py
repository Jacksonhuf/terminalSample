"""Outbound integration schema — messages, delivery results, outreach tasks."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ChannelType(str, Enum):
    CHAT = "chat"
    EMAIL = "email"


class OutboundMessage(BaseModel):
    channel: ChannelType
    recipients: list[str]
    subject: str = ""
    body: str
    template_id: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = ""
    object_type: str = ""
    object_id: str = ""


class DeliveryResult(BaseModel):
    success: bool
    channel: ChannelType
    recipients: list[str] = Field(default_factory=list)
    message_id: str = ""
    error: str = ""
    raw_output: str = ""


class MessageLogEntry(BaseModel):
    id: str
    timestamp: str
    channel: str
    template_id: str = ""
    recipients: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""
    status: str  # sent | failed | denied
    error: str = ""
    object_type: str = ""
    object_id: str = ""
    correlation_id: str = ""
    created_by: str = ""


class OutreachTask(BaseModel):
    id: str
    channel: ChannelType
    template_id: str
    recipients: list[str] = Field(default_factory=list)
    subject: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    object_type: str = ""
    object_id: str = ""
    person_id: str = ""
    due_at: str
    status: str  # pending | sent | failed | cancelled
    attempt_count: int = 0
    last_error: str = ""
    created_at: str = ""
    created_by_action: str = ""
    audit_id: str = ""
