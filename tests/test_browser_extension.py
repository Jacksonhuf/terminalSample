"""Tests for Browser Extension Action Adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from ontology_platform.connector.browser.manager import BrowserActionManager, build_browser_manager
from ontology_platform.connector.browser.schema import BrowserStepRequest, CreateBrowserRunRequest, PageState
from ontology_platform.connector.manager import ConnectorManager
from ontology_platform.connector.store import ConnectorStore

EXAMPLES = Path(__file__).parent.parent / "examples"
CONNECTOR_DIR = EXAMPLES / "connectors"


@pytest.fixture
def connector_store(tmp_path: Path) -> ConnectorStore:
    return ConnectorStore(tmp_path / "connector.db")


@pytest.fixture
def manager(connector_store: ConnectorStore) -> ConnectorManager:
    return ConnectorManager(CONNECTOR_DIR, connector_store, ontology_service=None)


@pytest.fixture
def browser_mgr(manager: ConnectorManager, tmp_path: Path) -> BrowserActionManager:
    return build_browser_manager(manager, tmp_path / "connector.db")


class TestBrowserDemoConnector:
    def test_load_browser_demo(self, manager: ConnectorManager):
        connector = manager.load_connector("browser_demo")
        assert connector.mode.value == "browser_extension"
        assert connector.browser_profile.drive_mode == "scripted"
        assert len(connector.browser_script) >= 3


class TestBrowserRunLifecycle:
    def test_create_run_returns_initial_command(self, browser_mgr: BrowserActionManager):
        result = browser_mgr.create_run(
            CreateBrowserRunRequest(connector="browser_demo", auto_sync=False)
        )
        run = result["run"]
        assert run["connector_name"] == "browser_demo"
        assert run["status"] == "pending"
        assert result["initial_command"]["action"] == "goto"

    def test_scripted_step_loop_and_ingest(self, browser_mgr: BrowserActionManager, connector_store: ConnectorStore):
        created = browser_mgr.create_run(
            CreateBrowserRunRequest(connector="browser_demo", auto_sync=False)
        )
        run_id = created["run"]["id"]

        resp1 = browser_mgr.process_step(run_id, BrowserStepRequest())
        assert resp1.command is not None
        assert resp1.command.action == "goto"
        assert resp1.done is False

        body = BrowserStepRequest(
            page_state=PageState(url="https://example.com", title="Example"),
            step_result={"action": "goto"},
        )
        completed = False
        for _ in range(8):
            step = browser_mgr.process_step(run_id, body)
            if step.done:
                completed = True
                break
            assert step.command is not None
            if step.command.action == "extract":
                body = BrowserStepRequest(
                    records=[
                        {
                            "record_type": "page_snapshot",
                            "external_id": "example-home",
                            "payload": {"title": "Example Domain", "external_id": "example-home"},
                        }
                    ],
                )
            else:
                body = BrowserStepRequest(
                    page_state=PageState(url="https://example.com", title="Example Domain"),
                    step_result={"action": step.command.action},
                )

        assert completed
        final = browser_mgr.get_run(run_id)
        assert final is not None
        assert final["status"] == "completed"
        assert final["records_captured"] >= 1

        row = connector_store.list_runs("browser_demo", limit=1)[0]
        assert row.records_captured >= 1

    def test_list_pending(self, browser_mgr: BrowserActionManager):
        browser_mgr.create_run(CreateBrowserRunRequest(connector="browser_demo", auto_sync=False))
        pending = browser_mgr.list_pending()
        assert len(pending) >= 1
        assert pending[0]["connector_name"] == "browser_demo"


class TestScriptedEngine:
    def test_template_rendering(self):
        from ontology_platform.connector.browser.schema import BrowserScriptStep
        from ontology_platform.connector.browser.step_engine import script_step_to_command

        step = BrowserScriptStep(action="goto", url="{{source_url}}")
        cmd = script_step_to_command(step, {"source_url": "https://example.com"})
        assert cmd.url == "https://example.com"
