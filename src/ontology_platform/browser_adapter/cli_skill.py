"""Install ontology-browser skill and manage local Bridge daemon."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ontology_platform.browser_adapter.skill_paths import skill_dir


def _default_url() -> str:
    return os.environ.get("BROWSER_BRIDGE_URL", "http://127.0.0.1:9920")


def _bridge_health(url: str, timeout: float = 3.0) -> dict | None:
    try:
        resp = httpx.get(url.rstrip("/") + "/health", timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _default_db_path() -> Path:
    return Path(os.environ.get("BROWSER_BRIDGE_DB", Path.home() / ".ontology" / "browser.db"))


def _spawn_bridge(host: str, port: int, db_path: Path) -> subprocess.Popen[bytes]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = db_path.parent / "bridge.log"
    log_file = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "ontology_platform.browser_adapter.__main__",
            "--host",
            host,
            "--port",
            str(port),
            "--db",
            str(db_path),
        ],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return proc


def cmd_ensure_bridge(url: str, wait_sec: float = 15.0) -> int:
    existing = _bridge_health(url)
    if existing:
        print(json_dump({"ok": True, "already_running": True, "health": existing, "url": url}))
        return 0

    normalized = url if "://" in url else f"http://{url}"
    parsed = urlparse(normalized)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 9920

    db_path = _default_db_path()
    proc = _spawn_bridge(host, port, db_path)
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        health = _bridge_health(url)
        if health:
            print(
                json_dump(
                    {
                        "ok": True,
                        "started": True,
                        "pid": proc.pid,
                        "url": url,
                        "db": str(db_path),
                        "log": str(db_path.parent / "bridge.log"),
                        "health": health,
                    }
                )
            )
            return 0
        if proc.poll() is not None:
            print(f"error: bridge process exited with code {proc.returncode}", file=sys.stderr)
            print(f"see log: {db_path.parent / 'bridge.log'}", file=sys.stderr)
            return 1
        time.sleep(0.5)

    print(f"error: bridge did not become healthy within {wait_sec}s", file=sys.stderr)
    return 1


def _copy_skill(dest: Path) -> None:
    src = skill_dir()
    if dest.resolve() == src.resolve():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def _resolve_install_target(target: str) -> Path:
    if target == "openclaw":
        base = Path(os.environ.get("OPENCLAW_SKILLS_DIR", Path.home() / ".openclaw" / "skills"))
        return base / "ontology-browser"
    if target == "hermes":
        base = Path(os.environ.get("HERMES_SKILLS_DIR", Path.home() / ".hermes" / "skills"))
        return base / "ontology-browser"
    if target == "auto":
        if (Path.home() / ".openclaw").is_dir():
            return Path.home() / ".openclaw" / "skills" / "ontology-browser"
        if (Path.home() / ".hermes").is_dir():
            return Path.home() / ".hermes" / "skills" / "ontology-browser"
        return Path.home() / ".local" / "share" / "ontology-browser" / "skill"
    return Path(target).expanduser()


def cmd_install_skill(target: str, skip_bridge: bool) -> int:
    dest = _resolve_install_target(target)
    _copy_skill(dest)
    result = {
        "ok": True,
        "skill_path": str(dest),
        "skill_md": str(dest / "SKILL.md"),
        "message": f"Skill copied to {dest}",
        "next": [
            "Load Chrome extension; set Bridge URL to BROWSER_BRIDGE_URL (default http://127.0.0.1:9920)",
            "Run: ontology-browser-client ensure-bridge && ontology-browser-client health",
        ],
    }
    print(json_dump(result))
    if not skip_bridge:
        return cmd_ensure_bridge(_default_url())
    return 0


def json_dump(obj: object) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install ontology-browser Agent Skill and manage local Bridge (no remote server)",
    )
    parser.add_argument(
        "--url",
        default=_default_url(),
        help="Local bridge URL (default env BROWSER_BRIDGE_URL or http://127.0.0.1:9920)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ensure-bridge", help="Start local bridge on this machine if not running")

    p_install = sub.add_parser("install-skill", help="Copy SKILL.md bundle into OpenClaw/Hermes skills dir")
    p_install.add_argument(
        "--target",
        default="auto",
        choices=["auto", "openclaw", "hermes"],
        help="Install destination (or pass a path as positional after --)",
    )
    p_install.add_argument("path", nargs="?", help="Custom skills directory path (overrides --target)")
    p_install.add_argument("--skip-bridge", action="store_true", help="Do not start local bridge after install")

    args = parser.parse_args()

    if args.cmd == "ensure-bridge":
        raise SystemExit(cmd_ensure_bridge(args.url))

    if args.cmd == "install-skill":
        target = args.path if args.path else args.target
        raise SystemExit(cmd_install_skill(target, args.skip_bridge))

    parser.error(f"unknown command: {args.cmd}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
