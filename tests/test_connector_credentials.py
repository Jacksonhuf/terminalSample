"""Tests for connector credential integration."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ontology_platform.connector.credential_resolver import build_login_task_payload, inject_credentials_env
from ontology_platform.connector.credential_store import CredentialStore
from ontology_platform.connector.manager import ConnectorManager
from ontology_platform.connector.schema import ConnectorDef, LoginConfig
from ontology_platform.connector.store import ConnectorStore

EXAMPLES = Path(__file__).parent.parent / "examples"
CONNECTOR_DIR = EXAMPLES / "connectors"


@pytest.fixture
def connector_dir(tmp_path: Path) -> Path:
    dest = tmp_path / "connectors"
    shutil.copytree(CONNECTOR_DIR, dest)
    return dest


@pytest.fixture
def credential_store(tmp_path: Path) -> CredentialStore:
    store = CredentialStore(tmp_path / "creds.db")
    store.create(
        name="ERP",
        username="ops",
        password="secret123",
        credential_id="cred-erp",
        login_url="https://erp.example.com/login",
    )
    return store


@pytest.fixture
def manager(
    tmp_path: Path, connector_dir: Path, credential_store: CredentialStore
) -> ConnectorManager:
    return ConnectorManager(
        connector_dir,
        ConnectorStore(tmp_path / "connector.db"),
        credential_store=credential_store,
    )


class TestComputerUseTaskCredentials:
    def test_task_includes_login_without_password(
        self, manager: ConnectorManager, connector_dir: Path
    ) -> None:
        connector = manager.load_connector("prototype_erp").model_copy(
            update={"credential_ref": "cred-erp"}
        )
        manager.save_connector(connector)
        task = manager.get_computer_use_task("prototype_erp")
        assert task["login"]["username"] == "ops"
        assert task["login"]["password_provided"] is True
        assert task["login"].get("password") is None

    def test_inject_credentials_env(self, credential_store: CredentialStore) -> None:
        connector = ConnectorDef(
            name="x",
            source_url="https://example.com",
            credential_ref="cred-erp",
            login=LoginConfig(login_url="https://erp.example.com/login"),
        )
        env = inject_credentials_env(connector, credential_store, env={})
        assert env["CU_USERNAME"] == "ops"
        assert env["CU_PASSWORD"] == "secret123"
        assert env["CU_LOGIN_URL"] == "https://erp.example.com/login"

    def test_build_login_without_credential(self) -> None:
        connector = ConnectorDef(name="x", source_url="https://example.com")
        payload = build_login_task_payload(connector, None)
        assert payload["password_provided"] is False
        assert payload["username"] == ""

    def test_find_credential_references(self, manager: ConnectorManager) -> None:
        connector = manager.load_connector("prototype_erp").model_copy(
            update={"credential_ref": "cred-erp"}
        )
        manager.save_connector(connector)
        refs = manager.find_credential_references("cred-erp")
        assert "prototype_erp" in refs
