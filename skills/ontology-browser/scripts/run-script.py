#!/usr/bin/env python3
"""Run a declarative browser script via local Bridge (for Agent exec)."""

from __future__ import annotations

import argparse
import json
import os
import sys

from ontology_platform.browser_adapter import BrowserAdapterClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scripted browser session on local Bridge")
    parser.add_argument("--url", default=os.environ.get("BROWSER_BRIDGE_URL", "http://127.0.0.1:9920"))
    parser.add_argument("--start-url", default="")
    parser.add_argument("--script", help="JSON array of script steps", required=True)
    args = parser.parse_args()

    script = json.loads(args.script)
    client = BrowserAdapterClient(args.url)
    session = client.run_script(script, start_url=args.start_url)
    print(json.dumps(session, ensure_ascii=False, indent=2))
    return 0 if session.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
