"""Business analytics for the prototype management app."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from ontology_platform.ontology.service import OntologyService


def build_dashboard(service: OntologyService) -> dict[str, Any]:
    """Aggregate prototype inventory stats without external dependencies."""
    prototypes = service.search_objects("Prototype", limit=500)
    reservations = service.search_objects("Reservation", limit=500)
    people = service.search_objects("Person", limit=200)
    projects = service.search_objects("Project", limit=100)

    by_status = Counter(p.properties.get("status", "unknown") for p in prototypes)
    by_model = Counter(p.properties.get("model", "unknown") for p in prototypes)

    in_use = [p for p in prototypes if p.properties.get("status") == "in_use"]
    custodian_ids: list[str] = []
    for proto in in_use:
        links = service.store.get_links(
            link_type="custodian", source_type="Prototype", source_id=proto.object_id
        )
        if links:
            custodian_ids.append(links[0].target_id)

    active_reservations = [r for r in reservations if r.properties.get("status") == "active"]
    today = date.today().isoformat()
    overdue_reservations = [
        r for r in active_reservations
        if r.properties.get("end_date", "") < today
    ]

    return {
        "summary": {
            "prototype_total": len(prototypes),
            "person_total": len(people),
            "project_total": len(projects),
            "reservation_active": len(active_reservations),
            "reservation_overdue": len(overdue_reservations),
        },
        "by_status": dict(by_status),
        "by_model": dict(by_model),
        "in_use": [
            {
                "prototype_id": p.object_id,
                "model": p.properties.get("model"),
                "custodian_id": custodian_ids[i] if i < len(custodian_ids) else None,
            }
            for i, p in enumerate(in_use)
        ],
        "overdue_reservations": [
            {
                "reservation_id": r.object_id,
                "prototype_id": r.properties.get("prototype_id"),
                "person_id": r.properties.get("person_id"),
                "end_date": r.properties.get("end_date"),
            }
            for r in overdue_reservations
        ],
    }


def format_dashboard_text(dashboard: dict[str, Any]) -> str:
    summary = dashboard["summary"]
    lines = [
        "📊 样机管理看板",
        f"- 样机总数: {summary['prototype_total']}",
        f"- 按状态: {dashboard['by_status']}",
        f"- 按型号: {dashboard['by_model']}",
        f"- 使用中: {len(dashboard['in_use'])} 台",
        f"- 活跃预约: {summary['reservation_active']} 条",
        f"- 逾期预约: {summary['reservation_overdue']} 条",
    ]
    if dashboard["overdue_reservations"]:
        lines.append("逾期预约明细:")
        for item in dashboard["overdue_reservations"]:
            lines.append(
                f"  - {item['reservation_id']}: 样机 {item['prototype_id']}, "
                f"预约人 {item['person_id']}, 截止 {item['end_date']}"
            )
    return "\n".join(lines)
