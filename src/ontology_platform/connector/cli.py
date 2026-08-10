"""CLI for data connector: task generation, ingest, sync."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ontology_platform.connector.credential_resolver import inject_credentials_env
from ontology_platform.connector.credential_store import CredentialStore
from ontology_platform.connector.manager import ConnectorManager
from ontology_platform.connector.schema import CaptureBatch
from ontology_platform.connector.store import ConnectorStore
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.service import OntologyService
from ontology_platform.ontology.store.sqlite import SQLiteStore


def _build_manager(
    connectors_dir: Path,
    db_path: Path,
    ontology_yaml: Path | None = None,
    ontology_db: Path | None = None,
    credential_db: Path | None = None,
) -> ConnectorManager:
    store = ConnectorStore(db_path)
    credential_store = CredentialStore(credential_db) if credential_db else None
    ontology_service = None
    if ontology_yaml is not None:
        registry = OntologyRegistry.from_yaml(ontology_yaml)
        names = registry.list_ontologies()
        if not names:
            raise ValueError(f"No ontology found in {ontology_yaml}")
        db = ontology_db or db_path.parent / f"{names[0]}.db"
        ontology_service = OntologyService(registry, names[0], store=SQLiteStore(str(db)))
    return ConnectorManager(connectors_dir, store, ontology_service, credential_store)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ontology-connector",
        description="Data connector: Computer Use capture → SQL → Ontology sync",
    )
    parser.add_argument(
        "--connectors-dir",
        default="examples/connectors",
        help="Directory with connector YAML definitions",
    )
    parser.add_argument(
        "--db",
        default="./data/connector.db",
        help="SQLite path for staged records",
    )
    parser.add_argument(
        "--ontology",
        default="examples/prototype_ontology.yaml",
        help="Ontology YAML for sync",
    )
    parser.add_argument(
        "--ontology-db",
        help="SQLite path for ontology objects (default: data/<ontology_name>.db)",
    )
    parser.add_argument(
        "--credential-db",
        help="SQLite path for encrypted credentials (default: --db parent/credentials.db)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_task = sub.add_parser("task", help="Generate Computer Use task for a connector")
    p_task.add_argument("connector", help="Connector name")
    p_task.add_argument("--json", action="store_true", help="Output as JSON")

    p_ingest = sub.add_parser("ingest", help="Ingest capture JSON into SQL staging")
    p_ingest.add_argument("capture_file", help="Path to capture JSON file")

    p_sync = sub.add_parser("sync", help="Sync staged records to ontology")
    p_sync.add_argument("connector", help="Connector name")
    p_sync.add_argument("--run-id", help="Specific run ID (default: all unsynced)")

    p_file = sub.add_parser("ingest-file", help="Ingest from a file connector's source_file")
    p_file.add_argument("connector", help="File connector name")

    p_status = sub.add_parser("status", help="Show connector run status")
    p_status.add_argument("connector", nargs="?", help="Filter by connector name")

    p_list = sub.add_parser("list", help="List available connectors")

    p_run = sub.add_parser("run", help="Execute LLM Computer Use capture (ingest + optional sync)")
    p_run.add_argument("connector", help="Connector name")
    p_run.add_argument("--mock", action="store_true", help="Use sample capture JSON (demo)")
    p_run.add_argument("--no-sync", action="store_true", help="Skip sync to ontology")
    p_run.add_argument("--llm-profile", help="LLM profile id (default profile if omitted)")

    p_daemon = sub.add_parser("daemon", help="Poll scheduled connector captures")
    p_daemon.add_argument("--interval", type=int, default=60, help="Poll interval in seconds")
    p_daemon.add_argument("--mock", action="store_true", help="Use mock capture for all runs")

    args = parser.parse_args(argv)
    connectors_dir = Path(args.connectors_dir)
    db_path = Path(args.db)
    ontology_yaml = Path(args.ontology) if args.ontology else None
    ontology_db = Path(args.ontology_db) if getattr(args, "ontology_db", None) else None
    credential_db = Path(args.credential_db) if getattr(args, "credential_db", None) else db_path.parent / "credentials.db"

    if args.command == "list":
        mgr = _build_manager(connectors_dir, db_path, credential_db=credential_db)
        for name in mgr.list_connectors():
            print(name)
        return 0

    if args.command == "task":
        mgr = _build_manager(connectors_dir, db_path, credential_db=credential_db)
        task = mgr.get_computer_use_task(args.connector)
        connector = mgr.load_connector(args.connector)
        env_note = inject_credentials_env(connector, mgr.credential_store)
        if args.json:
            print(json.dumps(task, ensure_ascii=False, indent=2))
        else:
            print(f"Connector: {task['connector']}")
            print(f"Run ID:    {task['run_id']}")
            print(f"URL:       {task['source_url']}")
            if task.get("login"):
                login = task["login"]
                print(f"Login URL: {login.get('login_url', '')}")
                print(f"Username:  {login.get('username', '')}")
                print(f"Password:  {'(via CU_PASSWORD env)' if login.get('password_provided') else '(not configured)'}")
            if env_note.get("CU_PASSWORD"):
                print("\nCredentials available via environment variables:")
                print("  CU_USERNAME, CU_PASSWORD, CU_LOGIN_URL (when configured)")
            print()
            print("Instructions:")
            print(task["instructions"])
            if task.get("hints"):
                print()
                print("Hints:")
                for hint in task["hints"]:
                    print(f"  - {hint}")
            print()
            print("Expected output format:")
            print(json.dumps(task["output_format"], ensure_ascii=False, indent=2))
        return 0

    if args.command == "ingest":
        mgr = _build_manager(connectors_dir, db_path, credential_db=credential_db)
        data = json.loads(Path(args.capture_file).read_text(encoding="utf-8"))
        batch = CaptureBatch.model_validate(data)
        result = mgr.ingest_batch(batch)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "sync":
        mgr = _build_manager(
            connectors_dir, db_path, ontology_yaml, ontology_db, credential_db=credential_db
        )
        result = mgr.sync_to_ontology(args.connector, run_id=args.run_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "ingest-file":
        mgr = _build_manager(
            connectors_dir, db_path, ontology_yaml, ontology_db, credential_db=credential_db
        )
        result = mgr.ingest_file(args.connector)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "status":
        store = ConnectorStore(db_path)
        runs = store.list_runs(connector_name=getattr(args, "connector", None))
        for r in runs:
            print(
                f"{r.id}  {r.connector_name}  {r.status}  "
                f"captured={r.records_captured} synced={r.records_synced}  {r.started_at}"
            )
        return 0

    if args.command == "run":
        mgr = _build_manager(
            connectors_dir, db_path, ontology_yaml, ontology_db, credential_db=credential_db
        )
        chat_model = _load_llm_model(credential_db, getattr(args, "llm_profile", None))
        result = mgr.run_capture(
            args.connector,
            chat_model=chat_model,
            mock=args.mock,
            auto_sync=not args.no_sync,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "daemon":
        from ontology_platform.connector.worker import run_capture_daemon

        mgr = _build_manager(
            connectors_dir, db_path, ontology_yaml, ontology_db, credential_db=credential_db
        )
        chat_model = _load_llm_model(credential_db, None)
        run_capture_daemon(
            mgr,
            chat_model=chat_model,
            mock=args.mock,
            interval=args.interval,
        )
        return 0

    return 1


def _load_llm_model(credential_db: Path, profile_id: str | None):
    """Load default LLM chat model when store path is available."""
    try:
        from ontology_platform.connector.credential_store import CredentialStore
        from ontology_platform.llm.factory import build_chat_model_from_store
        from ontology_platform.llm.store import LlmConfigStore

        store_path = credential_db
        if not store_path.exists():
            return None
        llm_store = LlmConfigStore(store_path)
        cred_store = CredentialStore(store_path)
        return build_chat_model_from_store(llm_store, cred_store, profile_id=profile_id)
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
