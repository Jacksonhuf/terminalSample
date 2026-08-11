#!/usr/bin/env python3
"""Example: drive Browser Extension via Python SDK (interactive mode).

Prerequisites:
  1. ontology-admin running: ontology-admin --port 8080 --connector-db ./data/connector.db
  2. Chrome extension loaded, bridge URL = http://127.0.0.1:8080, API v1

Usage:
  python examples/agents/browser_agent_demo.py
"""

from __future__ import annotations

import sys

from ontology_platform.browser_adapter.sdk import BrowserAdapterClient, open_interactive_session


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
    client = BrowserAdapterClient(base_url)

    print(f"Bridge: {base_url}")
    with open_interactive_session(client, start_url="https://example.com", metadata={"demo": True}) as session:
        print(f"Session: {session.session_id}")
        print("Requesting snapshot (extension must be polling)...")
        result = client.snapshot(session.session_id, wait_timeout_sec=60.0)
        if result:
            print(f"  URL: {result.url}")
            print(f"  Title: {result.title}")
            print(f"  Elements: {len(result.elements)}")
        else:
            print("  No page state returned")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
