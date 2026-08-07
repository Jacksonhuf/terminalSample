"""Channel adapter protocol for outbound integrations."""

from __future__ import annotations

from typing import Protocol

from ontology_platform.integrations.schema import DeliveryResult, OutboundMessage


class ChannelAdapter(Protocol):
    """Send an outbound message through a specific channel."""

    def send(self, message: OutboundMessage) -> DeliveryResult: ...
