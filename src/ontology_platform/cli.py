"""CLI for the ontology agent platform."""

from __future__ import annotations

import argparse
from pathlib import Path

from ontology_platform.platform import AgentPlatform


def main() -> None:
    parser = argparse.ArgumentParser(description="Ontology Agent Platform CLI")
    parser.add_argument(
        "--ontology",
        type=str,
        default=str(Path(__file__).parent.parent.parent / "examples" / "demo_ontology.yaml"),
        help="Path to ontology YAML file",
    )
    parser.add_argument("--seed", action="store_true", help="Seed demo data")
    parser.add_argument("--query", type=str, help="Single query mode (non-interactive)")
    args = parser.parse_args()

    platform = AgentPlatform.from_yaml(args.ontology)
    if args.seed:
        platform.seed_demo_data()
        print("✅ Demo data seeded.\n")

    if args.query:
        print(platform.chat(args.query))
        return

    print("Ontology Agent Platform (type 'quit' to exit)")
    print(f"Ontology: {platform.service.ontology.name}\n")

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
        print(f"Agent> {platform.chat(user_input)}\n")


if __name__ == "__main__":
    main()
