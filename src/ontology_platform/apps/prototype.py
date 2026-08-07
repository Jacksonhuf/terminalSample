"""样机管理应用 — 第一个垂直 Ontology 应用."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ontology_platform.agent.config import AgentConfig
from ontology_platform.integrations.factory import build_notification_service
from ontology_platform.integrations.schema import ChannelType
from ontology_platform.ontology.schema import ActionResult, OntologyObject
from ontology_platform.ontology.service import OntologyService
from ontology_platform.platform import AgentPlatform, ChatResult

if TYPE_CHECKING:
    from ontology_platform.integrations.notification import NotificationService

DEFAULT_ONTOLOGY = Path(__file__).parent.parent.parent.parent / "examples" / "prototype_ontology.yaml"

PROTOTYPE_STATUS = ("available", "reserved", "in_use", "maintenance", "retired")


class PrototypeApp:
    """样机管理智能体应用.

    Usage:
        app = PrototypeApp.create()
        app.seed()
        print(app.chat("查询所有可用样机"))
    """

    def __init__(
        self,
        platform: AgentPlatform,
        notification: NotificationService | None = None,
    ) -> None:
        self.platform = platform
        self.notification = notification
        self._handlers_registered = False

    @classmethod
    def create(
        cls,
        ontology_path: str | Path | None = None,
        config: AgentConfig | None = None,
        model=None,
        *,
        enable_notifications: bool = True,
        notification: NotificationService | None = None,
    ) -> PrototypeApp:
        path = ontology_path or DEFAULT_ONTOLOGY
        cfg = config or AgentConfig()
        platform = AgentPlatform.from_yaml(path, config=cfg, model=model)
        if notification is not None:
            ns = notification
        elif enable_notifications:
            ns = build_notification_service(cfg)
        else:
            ns = None
        app = cls(platform, ns)
        app.register_handlers()
        return app

    @property
    def service(self) -> OntologyService:
        return self.platform.get_service()

    def _sync_notification_context(self) -> None:
        if self.notification is not None:
            self.notification.set_execution_context(self.service.get_execution_context())

    def register_handlers(self) -> None:
        if self._handlers_registered:
            return
        ns = self.notification
        self.platform.register_action_handler(
            "ReservePrototype",
            lambda s, t, p: _reserve_handler(s, t, p, ns),
        )
        self.platform.register_action_handler(
            "CheckoutPrototype",
            lambda s, t, p: _checkout_handler(s, t, p, ns),
        )
        self.platform.register_action_handler(
            "ReturnPrototype",
            lambda s, t, p: _return_handler(s, t, p, ns),
        )
        self.platform.register_action_handler("RetirePrototype", _retire_handler)
        self.platform.register_action_handler(
            "NotifyCustodian",
            lambda s, t, p: _notify_custodian_handler(s, t, p, ns),
        )
        self.platform.register_action_handler(
            "SendChatMessage",
            lambda s, t, p: _send_chat_handler(s, t, p, ns),
        )
        self.platform.register_action_handler(
            "SendEmailReminder",
            lambda s, t, p: _send_email_reminder_handler(s, t, p, ns),
        )
        self.platform.register_action_handler(
            "ScheduleReminder",
            lambda s, t, p: _schedule_reminder_handler(s, t, p, ns),
        )
        self._handlers_registered = True

    def seed(self) -> None:
        """Seed sample prototype management data."""
        svc = self.service
        if svc.get_object("Person", "P-001"):
            return

        svc.create_object(
            "Person",
            {
                "id": "P-001",
                "name": "张三",
                "department": "研发部",
                "email": "zhangsan@example.com",
                "im_user_id": "zhangsan",
            },
            "P-001",
        )
        svc.create_object(
            "Person",
            {
                "id": "P-002",
                "name": "李四",
                "department": "测试部",
                "email": "lisi@example.com",
                "im_user_id": "lisi",
            },
            "P-002",
        )

        svc.create_object("Project", {"id": "PRJ-001", "name": "Alpha 项目", "status": "active"}, "PRJ-001")
        svc.create_object("Project", {"id": "PRJ-002", "name": "Beta 项目", "status": "active"}, "PRJ-002")

        svc.create_object("Location", {"id": "LOC-A1", "name": "A栋实验室", "building": "A"}, "LOC-A1")
        svc.create_object("Location", {"id": "LOC-B2", "name": "B栋测试间", "building": "B"}, "LOC-B2")

        prototypes = [
            {
                "id": "SN-2024-001",
                "serial_number": "SN-2024-001",
                "model": "X100",
                "status": "available",
                "firmware_version": "v1.2.0",
            },
            {
                "id": "SN-2024-002",
                "serial_number": "SN-2024-002",
                "model": "X100",
                "status": "in_use",
                "firmware_version": "v1.2.0",
            },
            {
                "id": "SN-2024-003",
                "serial_number": "SN-2024-003",
                "model": "X200",
                "status": "available",
                "firmware_version": "v2.0.1",
            },
            {
                "id": "SN-2024-004",
                "serial_number": "SN-2024-004",
                "model": "X200",
                "status": "maintenance",
                "firmware_version": "v2.0.0",
            },
        ]
        for props in prototypes:
            svc.create_object("Prototype", props, props["id"])

        svc.create_link("belongs_to", "Prototype", "SN-2024-001", "Project", "PRJ-001")
        svc.create_link("belongs_to", "Prototype", "SN-2024-002", "Project", "PRJ-001")
        svc.create_link("belongs_to", "Prototype", "SN-2024-003", "Project", "PRJ-002")
        svc.create_link("located_at", "Prototype", "SN-2024-001", "Location", "LOC-A1")
        svc.create_link("located_at", "Prototype", "SN-2024-002", "Location", "LOC-B2")
        svc.create_link("located_at", "Prototype", "SN-2024-003", "Location", "LOC-A1")
        svc.create_link("located_at", "Prototype", "SN-2024-004", "Location", "LOC-A1")
        svc.create_link("custodian", "Prototype", "SN-2024-002", "Person", "P-001")

    def chat(self, message: str, thread_id: str | None = None) -> str:
        self._sync_notification_context()
        return self.platform.chat(message, thread_id).response

    def chat_raw(self, message: str, thread_id: str | None = None) -> ChatResult:
        self._sync_notification_context()
        return self.platform.chat(message, thread_id)

    def resume(self, approved: bool = True, thread_id: str | None = None) -> str:
        self._sync_notification_context()
        return self.platform.resume(approved, thread_id).response

    def list_available(self) -> list:
        return self.service.search_objects("Prototype", {"status": "available"})


def _get_custodian_id(svc: OntologyService, prototype_id: str) -> str | None:
    links = svc.store.get_links(
        link_type="custodian", source_type="Prototype", source_id=prototype_id
    )
    if not links:
        return None
    return links[0].target_id


def _person_context(svc: OntologyService, person_id: str) -> dict:
    person = svc.get_object("Person", person_id)
    if person is None:
        return {"person_id": person_id, "person_name": person_id}
    return {
        "person_id": person_id,
        "person_name": person.properties.get("name", person_id),
    }


def _prototype_context(target: OntologyObject) -> dict:
    return {
        "prototype_id": target.object_id,
        "model": target.properties.get("model", ""),
        "status": target.properties.get("status", ""),
        "serial_number": target.properties.get("serial_number", target.object_id),
    }


def _update_prototype_status(
    svc: OntologyService, target: OntologyObject, status: str
) -> OntologyObject:
    props = dict(target.properties)
    props["status"] = status
    updated = OntologyObject(
        object_type=target.object_type,
        object_id=target.object_id,
        properties=props,
    )
    return svc.store.update_object(updated)


def _reserve_handler(
    svc: OntologyService,
    target: OntologyObject,
    params: dict,
    notification: NotificationService | None,
) -> ActionResult:
    if target.properties.get("status") != "available":
        return ActionResult(
            success=False,
            message=f"样机 {target.object_id} 当前状态为 {target.properties.get('status')}，无法预约",
        )

    person_id = params.get("person_id")
    if not person_id:
        return ActionResult(success=False, message="缺少 person_id 参数")
    if svc.get_object("Person", person_id) is None:
        return ActionResult(success=False, message=f"人员不存在: {person_id}")

    _update_prototype_status(svc, target, "reserved")

    reminder_id = None
    if notification and params.get("end_date"):
        end_date = params["end_date"]
        try:
            due = datetime.fromisoformat(f"{end_date}T00:00:00+00:00") + timedelta(days=1)
        except ValueError:
            due = datetime.now(timezone.utc) + timedelta(days=1)
        ctx = {
            **_prototype_context(target),
            **_person_context(svc, person_id),
            "start_date": params.get("start_date", ""),
            "end_date": end_date,
        }
        reminder_id = notification.schedule_reminder(
            channel=ChannelType.EMAIL,
            template_id="reserve_reminder",
            person_ids=[person_id],
            context=ctx,
            due_at=due.isoformat(),
            object_type="Prototype",
            object_id=target.object_id,
            person_id=person_id,
            created_by_action="ReservePrototype",
        )

    return ActionResult(
        success=True,
        message=(
            f"已预约样机 {target.object_id}，"
            f"预约人 {person_id}，"
            f"时段 {params.get('start_date')} ~ {params.get('end_date')}"
        ),
        data={"prototype_id": target.object_id, "reminder_id": reminder_id, **params},
    )


def _checkout_handler(
    svc: OntologyService,
    target: OntologyObject,
    params: dict,
    notification: NotificationService | None,
) -> ActionResult:
    status = target.properties.get("status")
    if status not in ("available", "reserved"):
        return ActionResult(
            success=False,
            message=f"样机 {target.object_id} 状态为 {status}，无法领用",
        )

    person_id = params.get("person_id")
    if not person_id:
        return ActionResult(success=False, message="缺少 person_id 参数")
    person = svc.get_object("Person", person_id)
    if person is None:
        return ActionResult(success=False, message=f"人员不存在: {person_id}")

    _update_prototype_status(svc, target, "in_use")

    svc.store.delete_links(
        link_type="custodian", source_type="Prototype", source_id=target.object_id
    )
    svc.create_link("custodian", "Prototype", target.object_id, "Person", person_id)

    if notification:
        notification.cancel_reminders(object_type="Prototype", object_id=target.object_id)

    return ActionResult(
        success=True,
        message=f"样机 {target.object_id} 已领用给 {person.properties.get('name', person_id)}",
        data={"prototype_id": target.object_id, "person_id": person_id},
    )


def _return_handler(
    svc: OntologyService,
    target: OntologyObject,
    params: dict,
    notification: NotificationService | None,
) -> ActionResult:
    if target.properties.get("status") != "in_use":
        return ActionResult(
            success=False,
            message=f"样机 {target.object_id} 未处于使用中，无法归还",
        )

    condition = params.get("condition", "good")
    _update_prototype_status(svc, target, "available")

    svc.store.delete_links(
        link_type="custodian", source_type="Prototype", source_id=target.object_id
    )

    if notification:
        notification.cancel_reminders(object_type="Prototype", object_id=target.object_id)

    return ActionResult(
        success=True,
        message=f"样机 {target.object_id} 已归还，状态: {condition}",
        data={"prototype_id": target.object_id, "condition": condition},
    )


def _retire_handler(
    svc: OntologyService, target: OntologyObject, params: dict
) -> ActionResult:
    if target.properties.get("status") == "retired":
        return ActionResult(success=False, message=f"样机 {target.object_id} 已报废")

    reason = params.get("reason", "")
    if not reason:
        return ActionResult(success=False, message="缺少报废原因")

    _update_prototype_status(svc, target, "retired")
    return ActionResult(
        success=True,
        message=f"样机 {target.object_id} 已报废，原因: {reason}",
        data={"prototype_id": target.object_id, "reason": reason},
    )


def _notify_custodian_handler(
    svc: OntologyService,
    target: OntologyObject,
    params: dict,
    notification: NotificationService | None,
) -> ActionResult:
    if notification is None:
        return ActionResult(success=False, message="通知服务未启用")

    custodian_id = _get_custodian_id(svc, target.object_id)
    if not custodian_id:
        return ActionResult(success=False, message=f"样机 {target.object_id} 无保管人")

    context = {
        **_prototype_context(target),
        **_person_context(svc, custodian_id),
        "extra_message": params.get("extra_message", ""),
    }
    result = notification.send_now(
        channel=ChannelType.CHAT,
        template_id="notify_custodian",
        person_ids=[custodian_id],
        context=context,
        service=svc,
        object_type="Prototype",
        object_id=target.object_id,
    )
    if not result.success:
        return ActionResult(success=False, message=f"发送失败: {result.error}")
    return ActionResult(
        success=True,
        message=f"已通过 IM 通知保管人 {custodian_id}",
        data={"prototype_id": target.object_id, "custodian_id": custodian_id},
    )


def _send_chat_handler(
    svc: OntologyService,
    target: OntologyObject,
    params: dict,
    notification: NotificationService | None,
) -> ActionResult:
    if notification is None:
        return ActionResult(success=False, message="通知服务未启用")

    person_id = params.get("person_id")
    message = params.get("message")
    if not person_id or not message:
        return ActionResult(success=False, message="缺少 person_id 或 message")

    ctx = svc.get_execution_context()
    context = {
        **_prototype_context(target),
        **_person_context(svc, person_id),
        "message": message,
        "sender_name": ctx.user_id,
    }
    result = notification.send_now(
        channel=ChannelType.CHAT,
        template_id="custom_message",
        person_ids=[person_id],
        context=context,
        service=svc,
        object_type="Prototype",
        object_id=target.object_id,
    )
    if not result.success:
        return ActionResult(success=False, message=f"发送失败: {result.error}")
    return ActionResult(
        success=True,
        message=f"已向 {person_id} 发送 IM 消息",
        data={"prototype_id": target.object_id, "person_id": person_id},
    )


def _send_email_reminder_handler(
    svc: OntologyService,
    target: OntologyObject,
    params: dict,
    notification: NotificationService | None,
) -> ActionResult:
    if notification is None:
        return ActionResult(success=False, message="通知服务未启用")

    person_id = params.get("person_id")
    reason = params.get("reason")
    if not person_id or not reason:
        return ActionResult(success=False, message="缺少 person_id 或 reason")

    context = {
        **_prototype_context(target),
        **_person_context(svc, person_id),
        "reason": reason,
        "due_date": params.get("due_date", ""),
    }
    result = notification.send_now(
        channel=ChannelType.EMAIL,
        template_id="reminder",
        person_ids=[person_id],
        context=context,
        service=svc,
        object_type="Prototype",
        object_id=target.object_id,
    )
    if not result.success:
        return ActionResult(success=False, message=f"发送失败: {result.error}")
    return ActionResult(
        success=True,
        message=f"已向 {person_id} 发送跟催邮件",
        data={"prototype_id": target.object_id, "person_id": person_id},
    )


def _schedule_reminder_handler(
    svc: OntologyService,
    target: OntologyObject,
    params: dict,
    notification: NotificationService | None,
) -> ActionResult:
    if notification is None:
        return ActionResult(success=False, message="通知服务未启用")

    person_id = params.get("person_id")
    reason = params.get("reason")
    due_at = params.get("due_at")
    if not person_id or not reason or not due_at:
        return ActionResult(success=False, message="缺少 person_id、reason 或 due_at")

    channel = params.get("channel", "email")
    if len(due_at) == 10:
        due_at = f"{due_at}T09:00:00+00:00"

    context = {
        **_prototype_context(target),
        **_person_context(svc, person_id),
        "reason": reason,
        "due_date": due_at[:10],
    }
    template_id = "reminder" if channel == "email" else "notify_custodian"
    task_id = notification.schedule_reminder(
        channel=ChannelType(channel),
        template_id=template_id,
        person_ids=[person_id],
        context=context,
        due_at=due_at,
        object_type="Prototype",
        object_id=target.object_id,
        person_id=person_id,
        created_by_action="ScheduleReminder",
    )
    return ActionResult(
        success=True,
        message=f"已预约 {channel} 跟催，任务 ID: {task_id}",
        data={"prototype_id": target.object_id, "task_id": task_id},
    )
