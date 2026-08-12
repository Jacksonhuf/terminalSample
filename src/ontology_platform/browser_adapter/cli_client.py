"""CLI for agents to call Browser Bridge without writing Python."""

from __future__ import annotations

import argparse
import json
import os
import sys

from ontology_platform.browser_adapter.sdk import BrowserAdapterClient


def _default_url() -> str:
    return os.environ.get("BROWSER_BRIDGE_URL", "http://127.0.0.1:9920")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Browser Adapter client CLI — call Bridge from shell or other agents",
    )
    parser.add_argument(
        "--url",
        default=_default_url(),
        help="Bridge base URL (or env BROWSER_BRIDGE_URL)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="GET /health on bridge")
    sub.add_parser("ensure-bridge", help="Start local bridge on this machine if not running")
    p_setup = sub.add_parser("setup", help="Install deps (optional), start bridge, show extension steps")
    p_setup.add_argument("--install", action="store_true", help="Run pip install -e .[browser] first")
    p_test = sub.add_parser("test-capture", help="Run demo scripted capture (needs Chrome extension)")
    p_test.add_argument("--timeout", type=float, default=120.0)
    p_test.add_argument("--skip-bridge", action="store_true")
    p_install = sub.add_parser("install-skill", help="Install SKILL.md for OpenClaw/Hermes (local machine)")
    p_install.add_argument("--target", default="auto", choices=["auto", "openclaw", "hermes"])
    p_install.add_argument("path", nargs="?", help="Custom install path")
    p_install.add_argument("--skip-bridge", action="store_true")

    p_create = sub.add_parser("create-session", help="Create browser session")
    p_create.add_argument("--mode", default="interactive", choices=["interactive", "scripted", "async"])
    p_create.add_argument("--start-url", default="")

    p_snap = sub.add_parser("snapshot", help="Send snapshot command (interactive session)")
    p_snap.add_argument("session_id")
    p_snap.add_argument("--timeout", type=float, default=60.0)

    p_get = sub.add_parser("get-session", help="Get session status")
    p_get.add_argument("session_id")

    args = parser.parse_args()

    if args.cmd == "ensure-bridge":
        from ontology_platform.browser_adapter.cli_skill import cmd_ensure_bridge

        raise SystemExit(cmd_ensure_bridge(args.url))

    if args.cmd == "install-skill":
        from ontology_platform.browser_adapter.cli_skill import cmd_install_skill

        target = args.path if args.path else args.target
        raise SystemExit(cmd_install_skill(target, args.skip_bridge))

    if args.cmd == "setup":
        from ontology_platform.browser_adapter.cli_quickstart import cmd_setup

        raise SystemExit(cmd_setup(args.url, getattr(args, "install", False)))

    if args.cmd == "test-capture":
        from ontology_platform.browser_adapter.cli_quickstart import cmd_test_capture

        raise SystemExit(cmd_test_capture(args.url, args.timeout, args.skip_bridge))

    client = BrowserAdapterClient(args.url)

    if args.cmd == "health":
        import httpx

        url = args.url.rstrip("/") + "/health"
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
        return

    if args.cmd == "create-session":
        result = client.create_session(mode=args.mode, start_url=args.start_url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.cmd == "snapshot":
        result = client.snapshot(args.session_id, wait_timeout_sec=args.timeout)
        print(json.dumps(result.model_dump() if result else None, ensure_ascii=False, indent=2))
        return

    if args.cmd == "get-session":
        result = client.get_session(args.session_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    parser.error(f"unknown command: {args.cmd}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
