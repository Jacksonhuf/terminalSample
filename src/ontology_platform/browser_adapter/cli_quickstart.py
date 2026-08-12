"""One-command setup and capture test for Browser Extension."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import yaml

from ontology_platform.browser_adapter.cli_skill import cmd_ensure_bridge, json_dump
from ontology_platform.browser_adapter.sdk import BrowserAdapterClient

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_CONNECTOR = REPO_ROOT / "examples" / "connectors" / "browser_demo.yaml"
DEFAULT_SCRIPT = [
    {"action": "goto", "url": "https://example.com"},
    {"action": "wait", "ms": 800},
    {"action": "snapshot"},
    {
        "action": "extract",
        "selector": "h1",
        "field": "title",
        "record_type": "page_snapshot",
        "external_id": "example-home",
    },
    {"action": "finish"},
]


ADMIN_DEFAULT_URL = "http://127.0.0.1:8080"
STANDALONE_DEFAULT_URL = "http://127.0.0.1:9920"


def _default_url() -> str:
    return os.environ.get("BROWSER_BRIDGE_URL", STANDALONE_DEFAULT_URL)


def _admin_url() -> str:
    return os.environ.get("ONTOLOGY_ADMIN_URL", ADMIN_DEFAULT_URL)


def _repo_root() -> Path:
    return REPO_ROOT if (REPO_ROOT / "pyproject.toml").is_file() else Path.cwd()


def _demo_script() -> tuple[list[dict], str]:
    if DEMO_CONNECTOR.is_file():
        data = yaml.safe_load(DEMO_CONNECTOR.read_text(encoding="utf-8"))
        script = data.get("browser_script") or DEFAULT_SCRIPT
        start_url = data.get("source_url") or "https://example.com"
        return script, start_url
    return DEFAULT_SCRIPT, "https://example.com"


def _print_admin_instructions(url: str) -> None:
    ext_dir = _repo_root() / "extension"
    print(
        f"""
╔══════════════════════════════════════════════════════════════╗
║  Browser Extension + Ontology Admin 联调（推荐）             ║
╠══════════════════════════════════════════════════════════════╣
║  1. 启动 Admin（另开终端）                                   ║
║     ontology-admin --port 8080 --connector-db ./data/connector.db
║  2. Chrome 扩展 Options                                      ║
║     • Bridge URL: {url}  （必须与 Admin 端口一致）
║     • API 版本: v1                                           ║
║  3. 测试采集 + 查看暂存数据                                  ║
║     ontology-browser-client test-admin-capture               ║
║     浏览器打开: {url}/admin/integration/mappings/discover
╚══════════════════════════════════════════════════════════════╝
"""
    )
    if ext_dir.is_dir():
        print(f"  扩展目录: {ext_dir.resolve()}\n")


def _print_setup_instructions(url: str) -> None:
    ext_dir = _repo_root() / "extension"
    release = "https://github.com/Jacksonhuf/terminalSample/releases/tag/browser-extension-v0.1.0"
    print(
        """
╔══════════════════════════════════════════════════════════════╗
║  Browser Extension 快速测试（3 步）                          ║
╠══════════════════════════════════════════════════════════════╣
║  1. 安装 Chrome 扩展                                         ║
║     • Release: 下载 browser-extension-*.zip 解压后加载        ║
║     • 开发: chrome://extensions → 加载已解压的 extension/     ║
║  2. 扩展 Options 设置                                        ║
║     • Bridge URL: {url}
║     • API 版本: v1                                           ║
║  3. 运行采集测试                                             ║
║     ontology-browser-client test-capture                     ║
║                                                              ║
║  ※ 若要与 Ontology Admin 联调，请用 Admin 8080 而非 9920：   ║
║     ontology-browser-client test-admin-capture               ║
╚══════════════════════════════════════════════════════════════╝
""".format(url=url)
    )
    if ext_dir.is_dir():
        print(f"  本地扩展目录: {ext_dir.resolve()}")
    print(f"  Release 下载: {release}\n")


def cmd_setup(url: str, install_deps: bool) -> int:
    if install_deps:
        root = _repo_root()
        print(f"Installing [browser] from {root} ...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", f"{root}[browser]"],
            check=True,
        )

    code = cmd_ensure_bridge(url)
    if code != 0:
        return code

    _print_setup_instructions(url)
    print(json_dump({"ok": True, "bridge_url": url, "next": "ontology-browser-client test-capture"}))
    return 0


def cmd_test_capture(url: str, timeout_sec: float, skip_bridge: bool) -> int:
    if not skip_bridge:
        if cmd_ensure_bridge(url) != 0:
            return 1

    script, start_url = _demo_script()
    print(f"Bridge: {url}")
    print(f"Target: {start_url}")
    print("Creating scripted session — Chrome 扩展需已连接并在轮询…\n")

    client = BrowserAdapterClient(url, timeout=max(60.0, timeout_sec))
    try:
        session = client.run_script(
            script,
            start_url=start_url,
            metadata={"demo": "test-capture"},
            max_wait_sec=timeout_sec,
        )
    except TimeoutError as exc:
        print(
            json_dump(
                {
                    "ok": False,
                    "error": str(exc),
                    "hint": "确认扩展 Options 里 Bridge URL 与上面一致，且扩展 popup 显示已连接",
                }
            )
        )
        return 1

    status = session.get("status")
    count = session.get("data_count", 0)
    collected = session.get("collected_data") or []
    result = {
        "ok": status == "completed" and count > 0,
        "status": status,
        "data_count": count,
        "collected_data": collected,
        "session_id": session.get("id"),
        "error": session.get("error") or "",
    }

    print(json_dump(result))

    if status == "completed" and count > 0:
        print("\n✓ 采集成功。示例数据：")
        for i, row in enumerate(collected[:3], 1):
            print(f"  [{i}] {json.dumps(row, ensure_ascii=False)[:200]}")
        return 0

    if status == "completed" and count == 0:
        print("\n✗ 任务完成但未采集到记录（检查页面 selector 或扩展是否执行 extract）", file=sys.stderr)
        return 1

    print(f"\n✗ 采集失败: {session.get('error') or status}", file=sys.stderr)
    return 1


def _poll_admin_run(base_url: str, run_id: str, timeout_sec: float) -> dict:
    import time

    deadline = time.time() + timeout_sec
    last: dict = {}
    while time.time() < deadline:
        resp = httpx.get(f"{base_url.rstrip('/')}/api/browser/runs/{run_id}", timeout=10.0)
        resp.raise_for_status()
        last = resp.json()
        if last.get("status") in ("completed", "failed"):
            return last
        time.sleep(1.5)
    raise TimeoutError(f"admin run {run_id} not finished within {timeout_sec}s")


def cmd_test_admin_capture(
    url: str,
    timeout_sec: float,
    simulate: bool,
    connector: str,
) -> int:
    base = url.rstrip("/")
    print(f"Ontology Admin: {base}")
    print(f"Connector: {connector}")
    print("Extension Bridge URL 必须设为同一地址（默认 8080）\n")

    try:
        health = httpx.get(f"{base}/v1/browser/sessions/pending", timeout=5.0)
        if health.status_code >= 500:
            raise httpx.HTTPError(f"admin not reachable: {health.status_code}")
    except httpx.HTTPError as exc:
        print(
            json_dump(
                {
                    "ok": False,
                    "error": str(exc),
                    "hint": "请先运行: ontology-admin --port 8080 --connector-db ./data/connector.db",
                }
            )
        )
        return 1

    created = httpx.post(
        f"{base}/api/connectors/{connector}/browser-run",
        json={"auto_sync": False},
        timeout=15.0,
    )
    if created.status_code == 404:
        print(json_dump({"ok": False, "error": f"connector not found: {connector}"}))
        return 1
    created.raise_for_status()
    payload = created.json()
    run_id = payload.get("run", {}).get("id") or payload.get("session", {}).get("id")
    if not run_id:
        print(json_dump({"ok": False, "error": "no run id returned", "payload": payload}))
        return 1

    print(f"Created run: {run_id}")
    if simulate:
        from ontology_platform.browser_adapter.extension_simulator import run_extension_simulation

        sim = run_extension_simulation(base, api="v1", run_id=run_id)
        final = _poll_admin_run(base, run_id, timeout_sec=10.0)
    else:
        print("等待 Chrome 扩展执行（最多 {}s）…".format(int(timeout_sec)))
        try:
            final = _poll_admin_run(base, run_id, timeout_sec)
        except TimeoutError as exc:
            print(
                json_dump(
                    {
                        "ok": False,
                        "error": str(exc),
                        "run_id": run_id,
                        "hint": "扩展 Bridge URL 是否为 {}？扩展是否已加载并在轮询？".format(base),
                    }
                )
            )
            return 1
        sim = None

    completion = final.get("completion") or {}
    captured = final.get("records_captured") or completion.get("records_captured") or 0

    staging = httpx.get(f"{base}/api/mappings/staging", timeout=10.0)
    staging.raise_for_status()
    staging_data = staging.json()

    connector_rows = [
        s
        for s in staging_data.get("summaries", [])
        if s.get("connector_name") == connector
    ]

    result = {
        "ok": final.get("status") == "completed" and captured > 0,
        "status": final.get("status"),
        "run_id": run_id,
        "records_captured": captured,
        "records_synced": completion.get("records_synced", 0),
        "completion": completion,
        "staging_for_connector": connector_rows,
        "mappings_url": f"{base}/admin/integration/mappings/discover",
        "simulated": simulate,
    }
    if sim:
        result["simulation"] = sim.get("session")

    print(json_dump(result))

    if result["ok"]:
        print(f"\n✓ Admin 采集成功：{captured} 条已写入暂存区")
        print(f"  在浏览器查看: {result['mappings_url']}")
        return 0

    print("\n✗ Admin 采集未成功", file=sys.stderr)
    return 1


def cmd_setup_admin(install_deps: bool) -> int:
    url = _admin_url()
    if install_deps:
        root = _repo_root()
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", f"{root}[browser]"], check=True)
    _print_admin_instructions(url)
    print(
        json_dump(
            {
                "ok": True,
                "admin_url": url,
                "extension_bridge_url": url,
                "start_admin": "ontology-admin --port 8080 --connector-db ./data/connector.db",
                "test": "ontology-browser-client test-admin-capture",
            }
        )
    )
    return 0


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Browser Extension quick setup and capture test")
    parser.add_argument("--url", default=_default_url(), help="Local bridge URL")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_setup = sub.add_parser("setup", help="Start local bridge and print extension setup steps")
    p_setup.add_argument("--install", action="store_true", help="pip install -e .[browser] first")
    p_setup.add_argument(
        "--admin",
        action="store_true",
        help="Print Ontology Admin + Extension instructions (port 8080, no standalone bridge)",
    )

    p_test = sub.add_parser("test-capture", help="Standalone bridge capture test (port 9920)")
    p_test.add_argument("--timeout", type=float, default=120.0, help="Max wait seconds")
    p_test.add_argument("--skip-bridge", action="store_true", help="Assume bridge already running")

    p_admin = sub.add_parser(
        "test-admin-capture",
        help="Test via Ontology Admin + browser_demo connector (extension on port 8080)",
    )
    p_admin.add_argument("--url", default=_admin_url(), help="Ontology Admin URL")
    p_admin.add_argument("--timeout", type=float, default=120.0)
    p_admin.add_argument("--simulate", action="store_true", help="Simulate extension (CI/dev, no Chrome)")
    p_admin.add_argument("--connector", default="browser_demo")

    args = parser.parse_args()
    if args.cmd == "setup":
        if getattr(args, "admin", False):
            raise SystemExit(cmd_setup_admin(args.install))
        raise SystemExit(cmd_setup(args.url, args.install))
    if args.cmd == "test-capture":
        raise SystemExit(cmd_test_capture(args.url, args.timeout, args.skip_bridge))
    if args.cmd == "test-admin-capture":
        raise SystemExit(
            cmd_test_admin_capture(args.url, args.timeout, args.simulate, args.connector)
        )
    parser.error(f"unknown: {args.cmd}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"error: install failed ({exc.returncode})", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
    except httpx.HTTPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
