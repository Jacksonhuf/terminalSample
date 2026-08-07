"""样机管理应用 — 第一个垂直 Ontology 应用."""

from __future__ import annotations

from pathlib import Path

from ontology_platform.agent.config import AgentConfig
from ontology_platform.ontology.schema import ActionResult, OntologyObject
from ontology_platform.ontology.service import OntologyService
from ontology_platform.platform import AgentPlatform, ChatResult

DEFAULT_ONTOLOGY = Path(__file__).parent.parent.parent.parent / "examples" / "prototype_ontology.yaml"

PROTOTYPE_STATUS = ("available", "reserved", "in_use", "maintenance", "retired")


class PrototypeApp:
    """样机管理智能体应用.

    Usage:
        app = PrototypeApp.create()
        app.seed()
        print(app.chat("查询所有可用样机"))
    """

    def __init__(self, platform: AgentPlatform) -> None:
        self.platform = platform
        self._handlers_registered = False

    @classmethod
    def create(
        cls,
        ontology_path: str | Path | None = None,
        config: AgentConfig | None = None,
        model=None,
    ) -> PrototypeApp:
        path = ontology_path or DEFAULT_ONTOLOGY
        platform = AgentPlatform.from_yaml(path, config=config, model=model)
        app = cls(platform)
        app.register_handlers()
        return app

    @property
    def service(self) -> OntologyService:
        return self.platform.get_service()

    def register_handlers(self) -> None:
        if self._handlers_registered:
            return
        self.platform.register_action_handler("ReservePrototype", _reserve_handler)
        self.platform.register_action_handler("CheckoutPrototype", _checkout_handler)
        self.platform.register_action_handler("ReturnPrototype", _return_handler)
        self.platform.register_action_handler("RetirePrototype", _retire_handler)
        self._handlers_registered = True

    def seed(self) -> None:
        """Seed sample prototype management data."""
        svc = self.service
        if svc.get_object("Person", "P-001"):
            return

        svc.create_object("Person", {"id": "P-001", "name": "张三", "department": "研发部"}, "P-001")
        svc.create_object("Person", {"id": "P-002", "name": "李四", "department": "测试部"}, "P-002")

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
        return self.platform.chat(message, thread_id).response

    def chat_raw(self, message: str, thread_id: str | None = None) -> ChatResult:
        return self.platform.chat(message, thread_id)

    def resume(self, approved: bool = True, thread_id: str | None = None) -> str:
        return self.platform.resume(approved, thread_id).response

    def list_available(self) -> list:
        return self.service.search_objects("Prototype", {"status": "available"})


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
    svc: OntologyService, target: OntologyObject, params: dict
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
    return ActionResult(
        success=True,
        message=(
            f"已预约样机 {target.object_id}，"
            f"预约人 {person_id}，"
            f"时段 {params.get('start_date')} ~ {params.get('end_date')}"
        ),
        data={"prototype_id": target.object_id, **params},
    )


def _checkout_handler(
    svc: OntologyService, target: OntologyObject, params: dict
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

    existing = svc.store.get_links(
        link_type="custodian", source_type="Prototype", source_id=target.object_id
    )
    svc.store.delete_links(
        link_type="custodian", source_type="Prototype", source_id=target.object_id
    )
    svc.create_link("custodian", "Prototype", target.object_id, "Person", person_id)

    return ActionResult(
        success=True,
        message=f"样机 {target.object_id} 已领用给 {person.properties.get('name', person_id)}",
        data={"prototype_id": target.object_id, "person_id": person_id},
    )


def _return_handler(
    svc: OntologyService, target: OntologyObject, params: dict
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
