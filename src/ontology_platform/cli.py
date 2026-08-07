"""CLI for the ontology agent platform."""

from __future__ import annotations

import argparse
from pathlib import Path

from ontology_platform.agent.config import AgentConfig
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
    parser.add_argument("--ontology", type=str, help="Path to ontology YAML file (overrides --app)")
    parser.add_argument("--seed", action="store_true", help="Seed demo data")
    parser.add_argument("--query", type=str, help="Single query mode (non-interactive)")
    parser.add_argument(
        "--store",
        type=str,
        help="SQLite database path for persistence",
    )
    parser.add_argument(
        "--planner",
        choices=["rule", "llm", "auto"],
        default="rule",
        help="Planner mode (default: rule)",
    )
    parser.add_argument(
        "--no-approval",
        action="store_true",
        help="Disable approval interrupt flow",
    )
    parser.add_argument(
        "--resume",
        choices=["approve", "reject"],
        help="Resume a pending approval for the thread",
    )
    parser.add_argument("--thread-id", type=str, default="default", help="Conversation thread ID")
    args = parser.parse_args()

    config = AgentConfig(
        planner_mode=args.planner,
        enable_approval_flow=not args.no_approval,
        store_path=args.store,
        thread_id=args.thread_id,
    )

    if args.resume:
        _resume_only(args, config)
        return

    if args.app == "prototype" and not args.ontology:
        app = PrototypeApp.create(config=config)
        if args.seed:
            app.seed()
            print("✅ Prototype data seeded.\n")
        chat_fn = app.chat
        resume_fn = app.resume
        ontology_name = app.service.ontology.name
        platform = app.platform
    else:
        ontology_path = args.ontology or str(EXAMPLES_DIR / "demo_ontology.yaml")
        platform = AgentPlatform.from_yaml(ontology_path, config=config)
        if args.seed:
            platform.seed_demo_data()
            print("✅ Demo data seeded.\n")
        chat_fn = lambda msg: platform.chat(msg, args.thread_id).response
        resume_fn = lambda approved: platform.resume(approved, args.thread_id).response
        ontology_name = platform.service.ontology.name

    if args.query:
        result = platform.chat(args.query, args.thread_id)
        print(result.response)
        if result.interrupted:
            print("\n(⏸️ 等待审批 — 使用 --resume approve 或 --resume reject)")
        return

    print("Ontology Agent Platform (type 'quit' to exit)")
    print(f"Ontology: {ontology_name} | Planner: {config.planner_mode}")
    if config.store_path:
        print(f"Store: {config.store_path}")
    print()

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
        if user_input.lower() in ("approve", "批准"):
            print(f"Agent> {resume_fn(True)}\n")
            continue
        if user_input.lower() in ("reject", "拒绝"):
            print(f"Agent> {resume_fn(False)}\n")
            continue
        result = platform.chat(user_input, args.thread_id)
        print(f"Agent> {result.response}\n")
        if result.interrupted:
            print("(输入 approve/批准 或 reject/拒绝 继续)\n")


def _resume_only(args, config: AgentConfig) -> None:
    if args.app == "prototype" and not args.ontology:
        app = PrototypeApp.create(config=config)
    else:
        ontology_path = args.ontology or str(EXAMPLES_DIR / "demo_ontology.yaml")
        app = AgentPlatform.from_yaml(ontology_path, config=config)
    approved = args.resume == "approve"
    platform = app.platform if hasattr(app, "platform") else app
    result = platform.resume(approved=approved, thread_id=args.thread_id)
    print(result.response)


if __name__ == "__main__":
    main()
