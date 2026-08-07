"""Tests for governance: audit logging and RBAC."""

import tempfile
from pathlib import Path

import pytest

from ontology_platform.agent.config import AgentConfig
from ontology_platform.apps.prototype import PrototypeApp
from ontology_platform.governance.audit import AuditLogger
from ontology_platform.governance.context import ExecutionContext
from ontology_platform.governance.policy import PolicyEngine
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.service import OntologyService

PROTOTYPE = Path(__file__).parent.parent / "examples" / "prototype_ontology.yaml"


@pytest.fixture
def service_with_governance():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        registry = OntologyRegistry.from_yaml(PROTOTYPE)
        audit = AuditLogger(db)
        svc = OntologyService(registry, "prototype", audit=audit, policy=PolicyEngine())
        yield svc, db


class TestPolicyEngine:
    def test_viewer_cannot_execute(self):
        registry = OntologyRegistry.from_yaml(PROTOTYPE)
        svc = OntologyService(registry, "prototype", policy=PolicyEngine())
        action = svc.ontology.get_action("ReturnPrototype")
        ctx = ExecutionContext(roles=["viewer"])
        allowed, msg = svc.policy.can_execute(action, ctx)
        assert allowed is False
        assert "viewer" in msg

    def test_admin_can_execute_retire(self):
        registry = OntologyRegistry.from_yaml(PROTOTYPE)
        svc = OntologyService(registry, "prototype", policy=PolicyEngine())
        action = svc.ontology.get_action("RetirePrototype")
        ctx = ExecutionContext(roles=["admin"])
        allowed, _ = svc.policy.can_execute(action, ctx)
        assert allowed is True

    def test_operator_cannot_retire(self):
        registry = OntologyRegistry.from_yaml(PROTOTYPE)
        svc = OntologyService(registry, "prototype", policy=PolicyEngine())
        action = svc.ontology.get_action("RetirePrototype")
        ctx = ExecutionContext(roles=["operator"])
        allowed, msg = svc.policy.can_execute(action, ctx)
        assert allowed is False

    def test_only_admin_can_approve(self):
        registry = OntologyRegistry.from_yaml(PROTOTYPE)
        svc = OntologyService(registry, "prototype", policy=PolicyEngine())
        action = svc.ontology.get_action("ReservePrototype")
        ctx = ExecutionContext(roles=["operator"])
        allowed, _ = svc.policy.can_approve(action, ctx)
        assert allowed is False


class TestAuditLog:
    def test_action_creates_audit_entry(self, service_with_governance):
        svc, db = service_with_governance
        svc.set_execution_context(ExecutionContext(user_id="u1", roles=["admin"]))
        svc.execute_action(
            "ReservePrototype",
            "SN-2024-001",
            {"person_id": "P-002", "start_date": "2026-08-10", "end_date": "2026-08-12"},
            approved=True,
        )
        logger = AuditLogger(db)
        logs = logger.query(action_name="ReservePrototype")
        assert len(logs) >= 1
        assert logs[0].user_id == "u1"
        assert logs[0].action_name == "ReservePrototype"

    def test_denied_action_logged(self, service_with_governance):
        svc, db = service_with_governance
        svc.create_object(
            "Prototype",
            {
                "id": "SN-TEST-001",
                "serial_number": "SN-TEST-001",
                "model": "X100",
                "status": "in_use",
            },
            "SN-TEST-001",
        )
        svc.set_execution_context(ExecutionContext(user_id="u2", roles=["viewer"]))
        result = svc.execute_action("ReturnPrototype", "SN-TEST-001", {"condition": "good"})
        assert result.denied is True
        logs = AuditLogger(db).query(user_id="u2")
        assert any(log.status == "denied" for log in logs)


class TestPlatformGovernance:
    def test_platform_audit_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = AgentConfig(store_path=str(Path(tmp) / "data.db"), enable_governance=True)
            app = PrototypeApp.create(PROTOTYPE, config=config)
            app.seed()
            app.platform.chat(
                "预约 SN-2024-003",
                user_id="tester",
                roles=["operator"],
            )
            logs = app.platform.get_audit_logs()
            assert len(logs) >= 1
