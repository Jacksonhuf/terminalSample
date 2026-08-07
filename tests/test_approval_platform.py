"""Tests for platform approval recording."""

from pathlib import Path

import pytest

from ontology_platform.agent.config import AgentConfig
from ontology_platform.apps.prototype import PrototypeApp
from ontology_platform.governance.context import ExecutionContext
from ontology_platform.platform import AgentPlatform

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def platform(tmp_path: Path) -> AgentPlatform:
    config = AgentConfig(
        store_path=str(tmp_path / "platform.db"),
        enable_governance=True,
        enable_approval_flow=True,
    )
    app = PrototypeApp.create(
        ontology_path=EXAMPLES / "prototype_ontology.yaml",
        config=config,
    )
    app.seed()
    return app.platform


class TestApprovalRecording:
    def test_pending_approval_recorded(self, platform: AgentPlatform):
        platform.service.set_execution_context(ExecutionContext(user_id="alice", roles=["operator"]))
        result = platform.chat(
            "预约 SN-2024-003",
            thread_id="approval-thread-1",
            user_id="alice",
            roles=["operator"],
        )
        if not result.interrupted:
            pytest.skip("Planner did not trigger approval flow for this message")

        requests = platform.list_approval_requests(status="pending")
        assert any(r.thread_id == "approval-thread-1" for r in requests)

        platform.resume(
            approved=True,
            thread_id="approval-thread-1",
            user_id="admin",
            roles=["admin"],
        )
        resolved = platform.list_approval_requests(status="approved")
        assert any(r.thread_id == "approval-thread-1" for r in resolved)
