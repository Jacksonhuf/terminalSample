"""CLI entry for ontology admin server."""

import argparse
from pathlib import Path

import uvicorn

from ontology_platform.admin.server import create_app

EXAMPLES_DIR = Path(__file__).parent.parent.parent.parent / "examples"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ontology Admin UI Server")
    parser.add_argument(
        "--dir",
        type=str,
        default=str(EXAMPLES_DIR),
        help="Ontology YAML directory",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8080, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument(
        "--store-path",
        type=str,
        default="",
        help="SQLite path for ontology objects, audit, and integrations (shorthand)",
    )
    parser.add_argument(
        "--audit-path",
        type=str,
        default="",
        help="Audit log SQLite path (default: --store-path)",
    )
    parser.add_argument(
        "--integrations-db",
        type=str,
        default="",
        help="Message log + outreach SQLite path (default: --store-path)",
    )
    parser.add_argument(
        "--ontology-yaml",
        type=str,
        default="",
        help="Ontology YAML for outreach worker (default: <dir>/prototype_ontology.yaml)",
    )
    parser.add_argument(
        "--ontology-db",
        type=str,
        default="",
        help="Ontology object SQLite for outreach worker",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default="",
        help="PostgreSQL URL for ontology store (e.g. postgresql://user:pass@localhost/db)",
    )
    parser.add_argument(
        "--connectors-dir",
        type=str,
        default="",
        help="Connector YAML directory (default: <dir>/connectors)",
    )
    parser.add_argument(
        "--credential-db",
        type=str,
        default="",
        help="SQLite path for encrypted credentials (default: --store-path)",
    )
    parser.add_argument(
        "--connector-db",
        type=str,
        default="",
        help="SQLite path for connector staging runs (default: data/connector.db)",
    )
    args = parser.parse_args()

    store_path = args.store_path or None
    audit_path = args.audit_path or store_path
    integrations_db = args.integrations_db or store_path
    ontology_yaml = args.ontology_yaml or None
    ontology_db = args.ontology_db or None
    database_url = args.database_url or None
    connectors_dir = args.connectors_dir or None
    credential_db = args.credential_db or store_path
    connector_db = args.connector_db or None

    app = create_app(
        args.dir,
        audit_path=audit_path,
        integrations_db_path=integrations_db,
        ontology_yaml_path=ontology_yaml,
        ontology_db_path=ontology_db,
        store_path=store_path,
        database_url=database_url,
        connectors_dir=connectors_dir,
        credential_db_path=credential_db,
        connector_db_path=connector_db,
    )
    print(f"\n  Ontology Admin UI: http://localhost:{args.port}/admin")
    print(f"  Ontology directory: {args.dir}")
    if audit_path:
        print(f"  Audit / integrations DB: {audit_path}")
    print(f"  Operations console: http://localhost:{args.port}/admin/operations/dashboard")
    print(f"  Data connectors: http://localhost:{args.port}/admin/integration/connectors")
    print(f"  Data mappings: http://localhost:{args.port}/admin/integration/mappings/discover")
    print(f"  LLM settings: http://localhost:{args.port}/admin/settings/llm\n")
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
