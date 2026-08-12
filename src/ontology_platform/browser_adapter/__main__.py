"""Standalone Browser Bridge server — Chrome Extension backend without full Admin UI."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ontology_platform.browser_adapter.api import build_browser_router
from ontology_platform.browser_adapter.bridge import build_browser_bridge


def create_bridge_app(db_path: str | Path) -> FastAPI:
    bridge = build_browser_bridge(db_path)
    app = FastAPI(
        title="Browser Action Adapter Bridge",
        description="Generic /v1/browser API for Chrome Extension and external agents",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(build_browser_router(bridge))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"ok": "true", "service": "browser-bridge"}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Browser Action Adapter Bridge — lightweight /v1/browser server",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (use 0.0.0.0 for LAN)")
    parser.add_argument("--port", type=int, default=9920, help="Bind port (default 9920)")
    parser.add_argument(
        "--db",
        default="browser.db",
        help="SQLite path for browser_sessions (default ./browser.db)",
    )
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev only)")
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    app = create_bridge_app(db_path)

    print(f"Browser Bridge listening on http://{args.host}:{args.port}")
    print(f"  Health:  http://{args.host}:{args.port}/health")
    print(f"  API:     http://{args.host}:{args.port}/v1/browser/sessions")
    print(f"  DB:      {db_path.resolve()}")
    print("Configure Chrome extension → Bridge URL → same host:port, API v1")

    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
