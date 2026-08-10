"""Tests for LLM Computer Use capture runner."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_platform.admin.server import create_app
from ontology_platform.connector.capture.runner import CaptureRunner
from ontology_platform.connector.manager import ConnectorManager
from ontology_platform.connector.store import ConnectorStore
from ontology_platform.connector.worker import run_due_scheduled_captures

EXAMPLES = Path(__file__).parent.parent / "examples"
CONNECTOR_DIR = EXAMPLES / "connectors"


@pytest.fixture
def connector_dir(tmp_path: Path) -> Path:
    dest = tmp_path / "connectors"
    shutil.copytree(CONNECTOR_DIR, dest)
    return dest


@pytest.fixture
def manager(tmp_path: Path, connector_dir: Path) -> ConnectorManager:
    return ConnectorManager(connector_dir, ConnectorStore(tmp_path / "connector.db"))


class TestCaptureRunnerMock:
    def test_mock_execute(self, manager: ConnectorManager):
        task = manager.get_computer_use_task("prototype_erp")
        runner = CaptureRunner(mock=True)
        batch = runner.execute(task, {})
        assert batch.connector == "prototype_erp"
        assert len(batch.records) == 3
        assert batch.metadata.get("mock") is True

    def test_run_capture_pipeline(self, manager: ConnectorManager):
        result = manager.run_capture("prototype_erp", mock=True, auto_sync=False)
        assert result["records_captured"] == 3
        runs = manager.store.list_runs("prototype_erp", limit=1)
        assert runs[0].status == "completed"


class TestCaptureWorker:
    def test_scheduled_capture_mock(self, manager: ConnectorManager, connector_dir: Path):
        import yaml

        path = connector_dir / "prototype_erp.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["schedule"] = {"enabled": True, "interval_sec": 60, "auto_sync": False}
        path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")

        summary = run_due_scheduled_captures(manager, mock=True)
        assert summary["processed"] == 1
        assert summary["results"][0]["status"] == "ok"


class TestCaptureAPI:
    def test_run_connector_mock(self, tmp_path: Path):
        connectors = tmp_path / "connectors"
        shutil.copytree(CONNECTOR_DIR, connectors)
        app = create_app(
            ontology_dir=tmp_path / "ontologies",
            connector_db_path=tmp_path / "connector.db",
            connectors_dir=connectors,
        )
        client = TestClient(app)
        res = client.post(
            "/api/connectors/prototype_erp/run",
            json={"mock": True, "auto_sync": False},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["records_captured"] == 3

    def test_list_connector_runs(self, tmp_path: Path):
        connectors = tmp_path / "connectors"
        shutil.copytree(CONNECTOR_DIR, connectors)
        app = create_app(
            connector_db_path=tmp_path / "connector.db",
            connectors_dir=connectors,
        )
        client = TestClient(app)
        client.post("/api/connectors/prototype_erp/run", json={"mock": True, "auto_sync": False})
        res = client.get("/api/connectors/prototype_erp/runs")
        assert res.status_code == 200
        assert res.json()["count"] >= 1
