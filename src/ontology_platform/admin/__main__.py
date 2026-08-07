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
    args = parser.parse_args()

    app = create_app(args.dir)
    print(f"\n  Ontology Admin UI: http://localhost:{args.port}")
    print(f"  Ontology directory: {args.dir}\n")
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
