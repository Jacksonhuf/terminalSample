"""Email adapter — SMTP or mail CLI."""

from __future__ import annotations

import shlex
import smtplib
import subprocess
from dataclasses import dataclass, field
from email.message import EmailMessage

from ontology_platform.integrations.schema import ChannelType, DeliveryResult, OutboundMessage


@dataclass
class EmailConfig:
    mode: str = "smtp"  # smtp | cli | mock
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_password: str = ""
    from_address: str = "ontology-platform@local"
    cli_command: str = "mail-cli"
    cli_send_template: str = "send --to {recipient} --subject {subject} --body {body}"
    timeout_seconds: int = 30
    mock_log: list[dict] = field(default_factory=list)


class EmailAdapter:
    """Send email via SMTP, external CLI, or in-memory mock (for tests)."""

    def __init__(self, config: EmailConfig | None = None) -> None:
        self.config = config or EmailConfig()

    def send(self, message: OutboundMessage) -> DeliveryResult:
        if not message.recipients:
            return DeliveryResult(
                success=False,
                channel=ChannelType.EMAIL,
                error="No recipients",
            )

        if self.config.mode == "mock":
            return self._send_mock(message)
        if self.config.mode == "cli":
            return self._send_cli(message)
        return self._send_smtp(message)

    def _send_mock(self, message: OutboundMessage) -> DeliveryResult:
        entry = {
            "recipients": list(message.recipients),
            "subject": message.subject,
            "body": message.body,
        }
        self.config.mock_log.append(entry)
        return DeliveryResult(
            success=True,
            channel=ChannelType.EMAIL,
            recipients=message.recipients,
            raw_output="mock sent",
        )

    def _send_cli(self, message: OutboundMessage) -> DeliveryResult:
        outputs: list[str] = []
        errors: list[str] = []
        for recipient in message.recipients:
            args = self.config.cli_send_template.format(
                recipient=shlex.quote(recipient),
                subject=shlex.quote(message.subject),
                body=shlex.quote(message.body),
            )
            cmd = f"{self.config.cli_command} {args}"
            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=self.config.timeout_seconds,
                    check=False,
                )
                outputs.append(proc.stdout)
                if proc.returncode != 0:
                    errors.append(f"{recipient}: {proc.stderr.strip() or proc.returncode}")
            except Exception as exc:
                errors.append(f"{recipient}: {exc}")

        return DeliveryResult(
            success=not errors,
            channel=ChannelType.EMAIL,
            recipients=message.recipients,
            error="; ".join(errors),
            raw_output="\n".join(outputs),
        )

    def _send_smtp(self, message: OutboundMessage) -> DeliveryResult:
        msg = EmailMessage()
        msg["From"] = self.config.from_address
        msg["To"] = ", ".join(message.recipients)
        msg["Subject"] = message.subject
        msg.set_content(message.body)
        try:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=self.config.timeout_seconds) as smtp:
                if self.config.smtp_user:
                    smtp.starttls()
                    smtp.login(self.config.smtp_user, self.config.smtp_password)
                smtp.send_message(msg)
            return DeliveryResult(
                success=True,
                channel=ChannelType.EMAIL,
                recipients=message.recipients,
            )
        except Exception as exc:
            return DeliveryResult(
                success=False,
                channel=ChannelType.EMAIL,
                recipients=message.recipients,
                error=str(exc),
            )
