"""Connector capture worker — manual and scheduled LLM Computer Use runs."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from ontology_platform.connector.manager import ConnectorManager


def run_connector_capture(
    manager: ConnectorManager,
    connector_name: str,
    *,
    chat_model: BaseChatModel | None = None,
    mock: bool = False,
    auto_sync: bool | None = None,
) -> dict[str, Any]:
    """Run a single capture pipeline for one connector."""
    return manager.run_capture(
        connector_name,
        chat_model=chat_model,
        mock=mock,
        auto_sync=auto_sync,
    )


def run_due_scheduled_captures(
    manager: ConnectorManager,
    *,
    chat_model: BaseChatModel | None = None,
    mock: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run captures for connectors whose schedule interval has elapsed."""
    now = now or datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for connector in manager.list_connector_defs():
        schedule = connector.schedule
        if schedule is None or not schedule.enabled:
            continue
        if connector.mode.value != "computer_use" and connector.mode.value != "file":
            continue

        last_runs = manager.store.list_runs(connector.name, limit=1)
        if last_runs:
            last = last_runs[0]
            if last.status == "running":
                continue
            try:
                started = datetime.fromisoformat(last.started_at.replace("Z", "+00:00"))
                elapsed = (now - started).total_seconds()
                if elapsed < schedule.interval_sec:
                    continue
            except ValueError:
                pass

        try:
            result = manager.run_capture(
                connector.name,
                chat_model=chat_model,
                mock=mock,
                auto_sync=schedule.auto_sync,
            )
            results.append({"connector": connector.name, "status": "ok", "result": result})
        except Exception as exc:
            errors.append(f"{connector.name}: {exc}")
            results.append({"connector": connector.name, "status": "failed", "error": str(exc)})

    return {"processed": len(results), "results": results, "errors": errors}


def run_capture_daemon(
    manager: ConnectorManager,
    *,
    chat_model: BaseChatModel | None = None,
    mock: bool = False,
    interval: int = 60,
) -> None:
    """Poll for due scheduled captures until interrupted."""
    print(f"Connector capture daemon started (poll={interval}s). Ctrl+C to stop.", flush=True)
    try:
        while True:
            summary = run_due_scheduled_captures(manager, chat_model=chat_model, mock=mock)
            if summary["processed"]:
                print(summary, flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Connector capture daemon stopped.", flush=True)
