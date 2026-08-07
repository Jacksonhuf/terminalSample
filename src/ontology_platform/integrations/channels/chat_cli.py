"""Internal IM chat adapter via CLI."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass

from ontology_platform.integrations.channels.base import ChannelAdapter
from ontology_platform.integrations.schema import ChannelType, DeliveryResult, OutboundMessage


@dataclass
class ChatCliConfig:
    command: str = "im-cli"
    send_template: str = "send --user {recipient} --text {body}"
    group_send_template: str = "send --group {recipient} --text {body}"
    timeout_seconds: int = 30


class ChatCliAdapter:
    """Wrap internal chat CLI for direct messages and group posts."""

    def __init__(self, config: ChatCliConfig | None = None) -> None:
        self.config = config or ChatCliConfig()

    def send(self, message: OutboundMessage) -> DeliveryResult:
        if not message.recipients:
            return DeliveryResult(
                success=False,
                channel=ChannelType.CHAT,
                error="No recipients",
            )

        outputs: list[str] = []
        errors: list[str] = []
        for recipient in message.recipients:
            result = self._send_one(recipient, message.body, message)
            outputs.append(result.raw_output)
            if not result.success:
                errors.append(f"{recipient}: {result.error}")

        return DeliveryResult(
            success=not errors,
            channel=ChannelType.CHAT,
            recipients=message.recipients,
            error="; ".join(errors),
            raw_output="\n".join(outputs),
        )

    def _send_one(self, recipient: str, body: str, message: OutboundMessage) -> DeliveryResult:
        template = self.config.group_send_template if recipient.startswith("group:") else self.config.send_template
        actual_recipient = recipient.removeprefix("group:")
        args_template = template.format(
            recipient=shlex.quote(actual_recipient),
            body=shlex.quote(body),
            subject=shlex.quote(message.subject),
        )
        cmd = f"{self.config.command} {args_template}"
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                check=False,
            )
            if proc.returncode != 0:
                return DeliveryResult(
                    success=False,
                    channel=ChannelType.CHAT,
                    recipients=[recipient],
                    error=proc.stderr.strip() or f"exit code {proc.returncode}",
                    raw_output=proc.stdout,
                )
            return DeliveryResult(
                success=True,
                channel=ChannelType.CHAT,
                recipients=[recipient],
                raw_output=proc.stdout.strip(),
            )
        except subprocess.TimeoutExpired:
            return DeliveryResult(
                success=False,
                channel=ChannelType.CHAT,
                recipients=[recipient],
                error="chat CLI timeout",
            )
        except Exception as exc:
            return DeliveryResult(
                success=False,
                channel=ChannelType.CHAT,
                recipients=[recipient],
                error=str(exc),
            )
