"""Tests for outbound integrations — chat, email, outreach."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ontology_platform.agent.config import AgentConfig
from ontology_platform.apps.prototype import PrototypeApp
from ontology_platform.governance.context import ExecutionContext
from ontology_platform.integrations.channels.email import EmailAdapter, EmailConfig
from ontology_platform.integrations.message_log import MessageLogStore
from ontology_platform.integrations.notification import NotificationService
from ontology_platform.integrations.outreach.store import OutreachStore
from ontology_platform.integrations.outreach.worker import process_due_tasks
from ontology_platform.integrations.policy import OutboundPolicy
from ontology_platform.integrations.schema import ChannelType, DeliveryResult, OutboundMessage
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.service import OntologyService
from ontology_platform.ontology.store.sqlite import SQLiteStore

EXAMPLES = Path(__file__).parent.parent / "examples"
ONTOLOGY_YAML = EXAMPLES / "prototype_ontology.yaml"


class MockChatAdapter:
    def __init__(self) -> None:
        self.messages: list[OutboundMessage] = []

    def send(self, message: OutboundMessage) -> DeliveryResult:
        self.messages.append(message)
        return DeliveryResult(
            success=True,
            channel=ChannelType.CHAT,
            recipients=message.recipients,
        )


@pytest.fixture
def ontology_service(tmp_path: Path) -> OntologyService:
    registry = OntologyRegistry.from_yaml(ONTOLOGY_YAML)
    svc = OntologyService(registry, "prototype", store=SQLiteStore(str(tmp_path / "proto.db")))
    svc.create_object(
        "Person",
        {
            "id": "P-001",
            "name": "张三",
            "email": "zhangsan@example.com",
            "im_user_id": "zhangsan",
        },
        "P-001",
    )
    svc.create_object(
        "Prototype",
        {
            "id": "SN-001",
            "serial_number": "SN-001",
            "model": "X100",
            "status": "in_use",
        },
        "SN-001",
    )
    svc.create_link("custodian", "Prototype", "SN-001", "Person", "P-001")
    return svc


@pytest.fixture
def notification(tmp_path: Path, ontology_service: OntologyService) -> NotificationService:
    email = EmailAdapter(EmailConfig(mode="mock"))
    chat = MockChatAdapter()
    ns = NotificationService(
        chat_adapter=chat,
        email_adapter=email,
        message_log=MessageLogStore(tmp_path / "integrations.db"),
        outreach_store=OutreachStore(tmp_path / "integrations.db"),
        policy=OutboundPolicy(),
        execution_context=ExecutionContext(user_id="tester", roles=["operator"]),
    )
    return ns


class TestNotificationService:
    def test_send_chat(self, notification: NotificationService, ontology_service: OntologyService):
        result = notification.send_now(
            channel=ChannelType.CHAT,
            template_id="notify_custodian",
            person_ids=["P-001"],
            context={
                "person_name": "张三",
                "prototype_id": "SN-001",
                "model": "X100",
                "status": "in_use",
                "extra_message": "请确认",
            },
            service=ontology_service,
            object_type="Prototype",
            object_id="SN-001",
        )
        assert result.success
        assert len(notification.chat_adapter.messages) == 1  # type: ignore[attr-defined]
        logs = notification.get_message_logs(object_type="Prototype", object_id="SN-001")
        assert len(logs) == 1
        assert logs[0].status == "sent"

    def test_send_email_mock(self, notification: NotificationService, ontology_service: OntologyService):
        result = notification.send_now(
            channel=ChannelType.EMAIL,
            template_id="reminder",
            person_ids=["P-001"],
            context={
                "person_name": "张三",
                "prototype_id": "SN-001",
                "model": "X100",
                "reason": "逾期未归还",
                "due_date": "2026-08-10",
            },
            service=ontology_service,
        )
        assert result.success
        assert len(notification.email_adapter.config.mock_log) == 1  # type: ignore[attr-defined]

    def test_policy_denies_viewer_email(self, notification: NotificationService, ontology_service: OntologyService):
        notification.set_execution_context(ExecutionContext(roles=["viewer"]))
        result = notification.send_now(
            channel=ChannelType.EMAIL,
            template_id="reminder",
            person_ids=["P-001"],
            context={"person_name": "张三", "prototype_id": "SN-001", "model": "X100", "reason": "test"},
            service=ontology_service,
        )
        assert not result.success
        assert "无权" in result.error or "viewer" in result.error.lower()


class TestOutreachWorker:
    def test_process_due_task(self, notification: NotificationService, ontology_service: OntologyService):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        notification.schedule_reminder(
            channel=ChannelType.EMAIL,
            template_id="reminder",
            person_ids=["P-001"],
            context={
                "person_name": "张三",
                "prototype_id": "SN-001",
                "model": "X100",
                "reason": "跟催测试",
                "due_date": "2026-08-10",
            },
            due_at=past,
            object_type="Prototype",
            object_id="SN-001",
        )
        result = process_due_tasks(notification, ontology_service)
        assert result["sent"] == 1
        tasks = notification.get_outreach_tasks(object_type="Prototype", object_id="SN-001")
        assert tasks[0].status == "sent"


class TestPrototypeNotificationActions:
    def _mock_app(self, tmp_path: Path) -> PrototypeApp:
        config = AgentConfig(
            store_path=str(tmp_path / "app.db"),
            integrations_db_path=str(tmp_path / "int.db"),
        )
        notification = NotificationService(
            chat_adapter=MockChatAdapter(),
            email_adapter=EmailAdapter(EmailConfig(mode="mock")),
            message_log=MessageLogStore(tmp_path / "int.db"),
            outreach_store=OutreachStore(tmp_path / "int.db"),
            execution_context=ExecutionContext(roles=["operator"]),
        )
        app = PrototypeApp.create(config=config, notification=notification)
        app.seed()
        app._sync_notification_context()
        return app

    def test_notify_custodian(self, tmp_path: Path):
        app = self._mock_app(tmp_path)
        app.service.set_execution_context(ExecutionContext(roles=["operator"]))
        result = app.service.execute_action("NotifyCustodian", "SN-2024-002", {})
        assert result.success

    def test_schedule_and_cancel_on_return(self, tmp_path: Path):
        app = self._mock_app(tmp_path)
        app.service.set_execution_context(ExecutionContext(roles=["operator"]))
        due = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        schedule = app.service.execute_action(
            "ScheduleReminder",
            "SN-2024-002",
            {"person_id": "P-001", "reason": "归还", "due_at": due},
        )
        assert schedule.success

        return_result = app.service.execute_action(
            "ReturnPrototype",
            "SN-2024-002",
            {"condition": "good"},
        )
        assert return_result.success

        pending = app.notification.get_outreach_tasks(
            object_type="Prototype", object_id="SN-2024-002", status="pending"
        )
        assert len(pending) == 0
