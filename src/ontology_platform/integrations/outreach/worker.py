"""Process due outreach / reminder tasks."""

from __future__ import annotations

from typing import Any

from ontology_platform.integrations.notification import NotificationService
from ontology_platform.integrations.schema import ChannelType
from ontology_platform.ontology.service import OntologyService


def process_due_tasks(
    notification: NotificationService,
    service: OntologyService,
    *,
    now: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Send all pending outreach tasks that are due."""
    tasks = notification.outreach_store.list_due(now=now, limit=limit)
    sent = 0
    failed = 0
    errors: list[str] = []

    for task in tasks:
        person_ids = task.recipients or ([task.person_id] if task.person_id else [])
        result = notification.send_now(
            channel=task.channel,
            template_id=task.template_id,
            person_ids=person_ids,
            context=task.context,
            service=service,
            object_type=task.object_type,
            object_id=task.object_id,
            correlation_id=task.id,
        )
        task.attempt_count += 1
        if result.success:
            task.status = "sent"
            task.last_error = ""
            sent += 1
        else:
            task.last_error = result.error
            if task.attempt_count >= 3:
                task.status = "failed"
            failed += 1
            errors.append(f"{task.id}: {result.error}")
        notification.outreach_store.update_task(task)

    return {"processed": len(tasks), "sent": sent, "failed": failed, "errors": errors}
