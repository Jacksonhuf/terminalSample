"""CLI for outreach worker and message inspection."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

from ontology_platform.agent.config import AgentConfig
from ontology_platform.integrations.factory import build_notification_service
from ontology_platform.integrations.outreach.worker import process_due_tasks
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.service import OntologyService
from ontology_platform.ontology.store.sqlite import SQLiteStore


def _build_services(
    db_path: str,
    ontology_yaml: str,
    ontology_db: str | None,
) -> tuple:
    config = AgentConfig(store_path=db_path, integrations_db_path=db_path)
    notification = build_notification_service(config)
    registry = OntologyRegistry.from_yaml(ontology_yaml)
    ontology_name = registry.list_ontologies()[0]
    resolved_db = ontology_db or str(Path(db_path).parent / f"{ontology_name}.db")
    service = OntologyService(registry, ontology_name, store=SQLiteStore(resolved_db))
    return notification, service


def _run_daemon(notification, service, interval: int) -> int:
    running = True

    def _stop(_signum, _frame) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    print(f"Outreach daemon started (interval={interval}s). Press Ctrl+C to stop.", flush=True)

    while running:
        result = process_due_tasks(notification, service)
        if result["processed"]:
            print(json.dumps(result, ensure_ascii=False), flush=True)
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)
    print("Outreach daemon stopped.", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ontology-outreach",
        description="Process due outreach reminders and inspect message logs",
    )
    parser.add_argument("--db", default="./data/integrations.db", help="Integrations SQLite path")
    parser.add_argument(
        "--ontology",
        default="examples/prototype_ontology.yaml",
        help="Ontology YAML for recipient resolution",
    )
    parser.add_argument(
        "--ontology-db",
        help="Ontology object store SQLite (default: data/<ontology_name>.db)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Process all due outreach tasks once")

    p_daemon = sub.add_parser("daemon", help="Run outreach worker loop")
    p_daemon.add_argument("--interval", type=int, default=60, help="Poll interval in seconds")

    p_logs = sub.add_parser("logs", help="Show message delivery logs")
    p_logs.add_argument("--object-type", default="")
    p_logs.add_argument("--object-id", default="")
    p_logs.add_argument("--limit", type=int, default=20)

    p_tasks = sub.add_parser("tasks", help="List outreach tasks")
    p_tasks.add_argument("--status", default="")
    p_tasks.add_argument("--object-type", default="")
    p_tasks.add_argument("--object-id", default="")

    args = parser.parse_args(argv)
    notification, service = _build_services(args.db, args.ontology, args.ontology_db)

    if args.command == "run":
        result = process_due_tasks(notification, service)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "daemon":
        return _run_daemon(notification, service, args.interval)

    if args.command == "logs":
        logs = notification.get_message_logs(
            object_type=args.object_type,
            object_id=args.object_id,
            limit=args.limit,
        )
        print(json.dumps([l.model_dump() for l in logs], ensure_ascii=False, indent=2))
        return 0

    if args.command == "tasks":
        tasks = notification.get_outreach_tasks(
            object_type=args.object_type,
            object_id=args.object_id,
            status=args.status or None,
        )
        print(json.dumps([t.model_dump() for t in tasks], ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
