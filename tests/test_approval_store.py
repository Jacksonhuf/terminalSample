"""Tests for approval request store."""

from pathlib import Path

import pytest

from ontology_platform.governance.approval_store import ApprovalStore


@pytest.fixture
def store(tmp_path: Path) -> ApprovalStore:
    return ApprovalStore(tmp_path / "approvals.db")


class TestApprovalStore:
    def test_create_and_list_pending(self, store: ApprovalStore):
        req = store.create_pending(
            thread_id="thread-1",
            action_name="ReservePrototype",
            target_id="SN-001",
            parameters={"person_id": "P-001"},
            requester_id="alice",
            requester_roles=["operator"],
        )
        assert req.status == "pending"
        pending = store.list_requests(status="pending")
        assert len(pending) == 1
        assert pending[0].action_name == "ReservePrototype"

    def test_resolve_request(self, store: ApprovalStore):
        req = store.create_pending(
            thread_id="thread-2",
            action_name="CheckoutPrototype",
            target_id="SN-002",
        )
        resolved = store.resolve(req.id, approved=True, resolver_id="admin", resolver_roles=["admin"])
        assert resolved is not None
        assert resolved.status == "approved"
        assert store.list_requests(status="pending") == []

    def test_resolve_by_thread(self, store: ApprovalStore):
        store.create_pending(thread_id="thread-3", action_name="RetirePrototype", target_id="SN-003")
        resolved = store.resolve_by_thread("thread-3", approved=False, resolver_id="boss")
        assert resolved is not None
        assert resolved.status == "rejected"
