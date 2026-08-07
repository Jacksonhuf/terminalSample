"""CLI for outreach worker and message inspection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ontology_platform.agent.config import AgentConfig
from ontology_platform.integrations.factory import build_notification_service
from ontology_platform.integrations.outreach.worker import process_due_tasks
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.service import OntologyService
from ontology_platform.ontology.store.sqlite import SQLiteStore


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
        help="Ontology object store SQLite (default: data/prototype.db)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Process all due outreach tasks")

    p_logs = sub.add_parser("logs", help="Show message delivery logs")
    p_logs.add_argument("--object-type", default="")
    p_logs.add_argument("--object-id", default="")
    p_logs.add_argument("--limit", type=int, default=20)

    p_tasks = sub.add_parser("tasks", help="List outreach tasks")
    p_tasks.add_argument("--status", default="")
    p_tasks.add_argument("--object-type", default="")
    p_tasks.add_argument("--object-id", default="")

    args = parser.parse_args(argv)
    config = AgentConfig(store_path=args.db, integrations_db_path=args.db)
    notification = build_notification_service(config)

    registry = OntologyRegistry.from_yaml(args.ontology)
    ontology_name = registry.list_ontologies()[0]
    ontology_db = args.ontology_db or str(Path(args.db).parent / f"{ontology_name}.db")
    service = OntologyService(registry, ontology_name, store=SQLiteStore(ontology_db))

    if args.command == "run":
        result = process_due_tasks(notification, service)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

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
