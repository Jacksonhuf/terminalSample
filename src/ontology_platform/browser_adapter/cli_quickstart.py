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


def _default_url() -> str:
    return os.environ.get("BROWSER_BRIDGE_URL", "http://127.0.0.1:9920")


def _repo_root() -> Path:
    return REPO_ROOT if (REPO_ROOT / "pyproject.toml").is_file() else Path.cwd()


def _demo_script() -> tuple[list[dict], str]:
    if DEMO_CONNECTOR.is_file():
        data = yaml.safe_load(DEMO_CONNECTOR.read_text(encoding="utf-8"))
        script = data.get("browser_script") or DEFAULT_SCRIPT
        start_url = data.get("source_url") or "https://example.com"
        return script, start_url
    return DEFAULT_SCRIPT, "https://example.com"


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


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Browser Extension quick setup and capture test")
    parser.add_argument("--url", default=_default_url(), help="Local bridge URL")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_setup = sub.add_parser("setup", help="Start local bridge and print extension setup steps")
    p_setup.add_argument("--install", action="store_true", help="pip install -e .[browser] first")

    p_test = sub.add_parser("test-capture", help="Run browser_demo scripted capture via extension")
    p_test.add_argument("--timeout", type=float, default=120.0, help="Max wait seconds")
    p_test.add_argument("--skip-bridge", action="store_true", help="Assume bridge already running")

    args = parser.parse_args()
    if args.cmd == "setup":
        raise SystemExit(cmd_setup(args.url, args.install))
    if args.cmd == "test-capture":
        raise SystemExit(cmd_test_capture(args.url, args.timeout, args.skip_bridge))
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
