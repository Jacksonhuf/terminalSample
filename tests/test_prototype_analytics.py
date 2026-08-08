"""样机看板与分析测试。"""

from __future__ import annotations

from ontology_platform.apps.prototype import PrototypeApp
from ontology_platform.governance.context import ExecutionContext


def test_dashboard_counts() -> None:
    app = PrototypeApp.create()
    app.seed()
    dash = app.get_dashboard()
    assert dash["summary"]["prototype_total"] == 4
    assert dash["by_status"]["available"] == 2
    assert dash["by_status"]["in_use"] == 1
    assert dash["by_model"]["X100"] == 2
    assert len(dash["in_use"]) == 1
    assert dash["summary"]["reservation_overdue"] == 0


def test_dashboard_text() -> None:
    app = PrototypeApp.create()
    app.seed()
    text = app.dashboard_text()
    assert "样机管理看板" in text
    assert "样机总数" in text


def test_reserve_creates_reservation() -> None:
    app = PrototypeApp.create()
    app.seed()
    app.service.set_execution_context(ExecutionContext(user_id="admin1", roles=["admin"]))
    result = app.service.execute_action(
        "ReservePrototype",
        "SN-2024-001",
        {"person_id": "P-002", "start_date": "2026-08-10", "end_date": "2026-08-12"},
        approved=True,
    )
    assert result.success is True
    reservations = app.service.search_objects("Reservation")
    assert len(reservations) == 1
    assert reservations[0].properties["status"] == "active"
    links = app.service.store.get_links(
        link_type="reserved_for", source_type="Reservation", source_id=reservations[0].object_id
    )
    assert len(links) == 1


def test_transfer_project() -> None:
    app = PrototypeApp.create()
    app.seed()
    result = app.service.execute_action(
        "TransferProject",
        "SN-2024-001",
        {"project_id": "PRJ-002"},
    )
    assert result.success is True
    links = app.service.traverse_links("Prototype", "SN-2024-001", "belongs_to")
    assert links[0]["object"]["object_id"] == "PRJ-002"


def test_start_and_complete_maintenance() -> None:
    app = PrototypeApp.create()
    app.seed()
    start = app.service.execute_action(
        "StartMaintenance",
        "SN-2024-001",
        {"reason": "更换主板"},
    )
    assert start.success is True
    proto = app.service.get_object("Prototype", "SN-2024-001")
    assert proto is not None
    assert proto.properties["status"] == "maintenance"

    complete = app.service.execute_action(
        "CompleteMaintenance",
        "SN-2024-001",
        {"notes": "已修好"},
    )
    assert complete.success is True
    proto = app.service.get_object("Prototype", "SN-2024-001")
    assert proto is not None
    assert proto.properties["status"] == "available"


def test_checkout_completes_reservation() -> None:
    app = PrototypeApp.create()
    app.seed()
    app.service.set_execution_context(ExecutionContext(user_id="admin1", roles=["admin"]))
    app.service.execute_action(
        "ReservePrototype",
        "SN-2024-003",
        {"person_id": "P-002", "start_date": "2026-08-10", "end_date": "2026-08-12"},
        approved=True,
    )
    app.service.execute_action(
        "CheckoutPrototype",
        "SN-2024-003",
        {"person_id": "P-002"},
        approved=True,
    )
    reservations = app.service.search_objects("Reservation")
    assert reservations[0].properties["status"] == "completed"


def test_dashboard_chat() -> None:
    app = PrototypeApp.create()
    app.seed()
    response = app.chat("样机看板统计")
    assert "看板" in response or "样机总数" in response
