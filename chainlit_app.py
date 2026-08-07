"""Chainlit chat UI for the ontology agent platform.

Run:
    chainlit run chainlit_app.py

Environment variables:
    ONTOLOGY_APP=prototype|demo     (default: prototype)
    ONTOLOGY_STORE_PATH=./data.db   (optional SQLite persistence)
    ONTOLOGY_SEED=true              (seed demo data on startup)
    ONTOLOGY_USER_ID=anonymous      (fallback user when Chainlit auth disabled)
    ONTOLOGY_USER_ROLES=operator    (fallback roles, comma-separated)
    ONTOLOGY_APPROVER_ROLES=admin   (approver roles when auth disabled)
    ONTOLOGY_ROLE_MAP={}            (optional JSON map prefix -> roles)
"""

from __future__ import annotations

import os
from pathlib import Path

import chainlit as cl

from ontology_platform.agent.config import AgentConfig
from ontology_platform.apps.prototype import PrototypeApp
from ontology_platform.chat.chainlit_helpers import summarize_chat_result
from ontology_platform.chat.identity import resolve_approver_identity, resolve_chainlit_identity
from ontology_platform.platform import AgentPlatform

EXAMPLES_DIR = Path(__file__).parent / "examples"


def _build_app():
    app_name = os.getenv("ONTOLOGY_APP", "prototype")
    store_path = os.getenv("ONTOLOGY_STORE_PATH")
    integrations_db = os.getenv("ONTOLOGY_INTEGRATIONS_DB") or store_path
    config = AgentConfig(
        store_path=store_path,
        integrations_db_path=integrations_db,
        enable_approval_flow=True,
        enable_governance=True,
    )

    if app_name == "demo":
        platform = AgentPlatform.from_yaml(EXAMPLES_DIR / "demo_ontology.yaml", config=config)
        if os.getenv("ONTOLOGY_SEED", "true").lower() == "true":
            platform.seed_demo_data()
        return platform, "demo"

    app = PrototypeApp.create(config=config)
    if os.getenv("ONTOLOGY_SEED", "true").lower() == "true":
        app.seed()
    return app.platform, "prototype"


@cl.on_chat_start
async def on_chat_start():
    platform, app_name = _build_app()
    user_id, roles = resolve_chainlit_identity()
    cl.user_session.set("platform", platform)
    cl.user_session.set("app_name", app_name)
    cl.user_session.set("thread_id", cl.context.session.id)
    cl.user_session.set("user_id", user_id)
    cl.user_session.set("roles", roles)

    ontology = platform.service.ontology
    await cl.Message(
        content=(
            f"👋 **Ontology 智能体已就绪**\n\n"
            f"- 应用: `{app_name}`\n"
            f"- 本体: `{ontology.name}` v{ontology.version}\n"
            f"- 当前用户: `{user_id}` | 角色: `{', '.join(roles)}`\n"
            f"- 对象类型: {len(ontology.object_types)} 个\n"
            f"- 可执行动作: {len(ontology.actions)} 个\n\n"
            f"你可以查询样机、遍历关系，或执行预约/领用等操作。\n"
            f"写操作若需审批，会弹出批准/拒绝按钮。"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    platform: AgentPlatform = cl.user_session.get("platform")
    thread_id: str = cl.user_session.get("thread_id")
    user_id, roles = resolve_chainlit_identity()
    cl.user_session.set("user_id", user_id)
    cl.user_session.set("roles", roles)

    async with cl.Step(name="意图识别 & 规划", type="tool") as plan_step:
        result = platform.chat(
            message.content,
            thread_id=thread_id,
            user_id=user_id,
            roles=roles,
        )
        summary = summarize_chat_result(result)
        plan_step.output = (
            f"**意图**: `{summary['intent']}`\n\n"
            f"**执行计划**:\n{summary['plan']}"
        )

    async with cl.Step(name="Ontology 执行", type="tool") as exec_step:
        exec_step.output = summary["execution"]

    if result.interrupted:
        await cl.Message(content=summary["response"]).send()
        action_res = await cl.AskActionMessage(
            content=f"### 审批请求\n\n{summary['approval']}",
            actions=[
                cl.Action(name="approve", payload={"approved": True}, label="✅ 批准"),
                cl.Action(name="reject", payload={"approved": False}, label="❌ 拒绝"),
            ],
        ).send()

        approved = bool(action_res.get("payload", {}).get("approved"))
        approver_id, approver_roles = resolve_approver_identity()
        async with cl.Step(name="审批处理", type="tool") as approval_step:
            approval_step.output = (
                f"{'已批准' if approved else '已拒绝'} "
                f"(审批人: {approver_id}, 角色: {', '.join(approver_roles)})"
            )
            final = platform.resume(
                approved=approved,
                thread_id=thread_id,
                user_id=approver_id,
                roles=approver_roles,
            )
            final_summary = summarize_chat_result(final)

        await cl.Message(content=final_summary["response"]).send()
        return

    await cl.Message(content=summary["response"]).send()
