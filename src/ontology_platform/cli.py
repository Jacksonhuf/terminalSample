"""CLI for the ontology agent platform."""

from __future__ import annotations

import argparse
from pathlib import Path

from ontology_platform.apps.prototype import PrototypeApp
from ontology_platform.platform import AgentPlatform

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ontology Agent Platform CLI")
    parser.add_argument(
        "--app",
        choices=["demo", "prototype"],
        default="demo",
        help="Application to run (default: demo)",
    )
    parser.add_argument(
        "--ontology",
        type=str,
        help="Path to ontology YAML file (overrides --app)",
    )
    parser.add_argument("--seed", action="store_true", help="Seed demo data")
    parser.add_argument("--query", type=str, help="Single query mode (non-interactive)")
    args = parser.parse_args()

    if args.app == "prototype" and not args.ontology:
        app = PrototypeApp.create()
        if args.seed:
            app.seed()
            print("✅ Prototype data seeded.\n")
        chat_fn = app.chat
        ontology_name = app.service.ontology.name
    else:
        ontology_path = args.ontology or str(EXAMPLES_DIR / "demo_ontology.yaml")
        platform = AgentPlatform.from_yaml(ontology_path)
        if args.seed:
            platform.seed_demo_data()
            print("✅ Demo data seeded.\n")
        chat_fn = platform.chat
        ontology_name = platform.service.ontology.name

    if args.query:
        print(chat_fn(args.query))
        return

    print("Ontology Agent Platform (type 'quit' to exit)")
    print(f"Ontology: {ontology_name}\n")

    while True:
        try:
            user_input = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break
        print(f"Agent> {chat_fn(user_input)}\n")


if __name__ == "__main__":
    main()
