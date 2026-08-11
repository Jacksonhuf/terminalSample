"""Browser Action Adapter — Ontology connector integration over generic BrowserBridge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ontology_platform.browser_adapter.bridge import BrowserBridge, build_browser_bridge
from ontology_platform.browser_adapter.schema import CreateSessionRequest
from ontology_platform.connector.browser.schema import (
    BrowserDriveMode,
    BrowserRunPublic,
    BrowserRunStatus,
    BrowserStepRequest,
    BrowserStepResponse,
    CreateBrowserRunRequest,
)
from ontology_platform.connector.manager import ConnectorManager
from ontology_platform.connector.schema import CaptureBatch, CaptureMode, CaptureRecord, ConnectorDef


def _session_to_run_public(session: dict[str, Any]) -> BrowserRunPublic:
    meta = session.get("metadata") or {}
    status = _map_status(session.get("status", "pending"))
    return BrowserRunPublic(
        id=session["id"],
        connector_name=meta.get("connector_name", ""),
        status=status,
        drive_mode=meta.get("drive_mode", "scripted"),  # type: ignore[arg-type]
        action_name=meta.get("action_name", ""),
        source_url=session.get("start_url", ""),
        connector_run_id=meta.get("connector_run_id", ""),
        step_index=session.get("step_index", 0),
        step_total=session.get("step_total", 0),
        records_captured=session.get("data_count", 0),
        error=session.get("error", ""),
        started_at=session.get("started_at", ""),
        finished_at=session.get("finished_at", ""),
    )


def _map_status(status: str) -> BrowserRunStatus:
    mapping = {
        "pending": BrowserRunStatus.PENDING,
        "running": BrowserRunStatus.RUNNING,
        "waiting_agent": BrowserRunStatus.RUNNING,
        "waiting_extension": BrowserRunStatus.RUNNING,
        "completed": BrowserRunStatus.COMPLETED,
        "failed": BrowserRunStatus.FAILED,
        "cancelled": BrowserRunStatus.FAILED,
    }
    return mapping.get(status, BrowserRunStatus.RUNNING)


class BrowserActionManager:
    """Ontology-facing wrapper over generic BrowserBridge."""

    def __init__(
        self,
        connector_mgr: ConnectorManager,
        bridge: BrowserBridge,
    ) -> None:
        self.connector_mgr = connector_mgr
        self.bridge = bridge

    @property
    def bridge_instance(self) -> BrowserBridge:
        return self.bridge

    def create_run(self, req: CreateBrowserRunRequest) -> dict[str, Any]:
        connector = self.connector_mgr.load_connector(req.connector)
        if connector.mode not in (CaptureMode.BROWSER_EXTENSION, CaptureMode.COMPUTER_USE):
            pass

        drive_mode: BrowserDriveMode = req.drive_mode or self._default_drive_mode(connector)
        source_url = req.source_url or connector.source_url
        steps, action_name = self._resolve_steps(connector, req.action_name, req.parameters)

        mode = "scripted" if drive_mode == "scripted" and steps else "async"
        from ontology_platform.connector.browser.schema import BrowserScriptStep

        session_req = CreateSessionRequest(
            mode=mode,  # type: ignore[arg-type]
            start_url=source_url,
            script=[BrowserScriptStep.model_validate(s) for s in steps],
            parameters={**req.parameters, "start_url": source_url},
            metadata={
                "connector_name": connector.name,
                "drive_mode": drive_mode,
                "action_name": action_name or req.action_name,
                "auto_sync": req.auto_sync,
                "source_url": source_url,
            },
        )
        result = self.bridge.create_session(session_req)
        run = _session_to_run_public(result["session"])
        return {
            "run": run.model_dump(),
            "session": result["session"],
            "initial_command": result.get("initial_command"),
        }

    def list_pending(self, limit: int = 20) -> list[dict[str, Any]]:
        return [_session_to_run_public(s).model_dump() for s in self.bridge.list_pending(limit)]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        session = self.bridge.get_session(run_id)
        if session is None:
            return None
        return _session_to_run_public(session).model_dump()

    def heartbeat(self, run_id: str) -> None:
        self.bridge.heartbeat(run_id)

    def process_step(self, run_id: str, body: BrowserStepRequest) -> BrowserStepResponse:
        from ontology_platform.browser_adapter.schema import StepSubmitRequest

        step_req = StepSubmitRequest(
            page_state=body.page_state,
            step_result=body.step_result,
            records=body.records,
            error=body.error,
        )
        resp = self.bridge.process_step(run_id, step_req)
        return BrowserStepResponse(
            run_id=resp.session_id,
            status=_map_status(resp.status),
            command=resp.command,
            done=resp.done,
            message=resp.message,
        )

    def _default_drive_mode(self, connector: ConnectorDef) -> BrowserDriveMode:
        if connector.browser_profile.drive_mode:
            return connector.browser_profile.drive_mode  # type: ignore[return-value]
        if connector.browser_actions:
            return "scripted"
        return "agent_loop"

    def _resolve_steps(
        self,
        connector: ConnectorDef,
        action_name: str,
        parameters: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], str]:
        if action_name:
            for action in connector.browser_actions:
                if action.name == action_name:
                    steps = [s.model_dump() for s in action.steps]
                    return steps, action.name
            raise ValueError(f"browser action not found: {action_name}")

        if connector.browser_script:
            return [s.model_dump() for s in connector.browser_script], ""

        if connector.browser_actions:
            steps = [s.model_dump() for s in connector.browser_actions[0].steps]
            return steps, connector.browser_actions[0].name

        return [], ""


def _build_ingest_handler(connector_mgr: ConnectorManager):
    def on_complete(session_id: str, metadata: dict[str, Any], collected: list[dict[str, Any]]) -> dict[str, Any]:
        connector_name = metadata.get("connector_name")
        if not connector_name:
            return {"message": "completed", "records": len(collected)}

        connector = connector_mgr.load_connector(connector_name)
        records = []
        for item in collected:
            records.append(
                CaptureRecord(
                    record_type=item.get("record_type", item.get("type", "record")),
                    external_id=str(item.get("external_id", item.get("id", "unknown"))),
                    payload=item.get("payload") or item,
                )
            )

        connector_run_id = metadata.get("connector_run_id") or connector_mgr.start_run(connector_name)
        batch = CaptureBatch(
            connector=connector_name,
            run_id=connector_run_id,
            source_url=metadata.get("source_url", connector.source_url),
            records=records,
        )
        ingest = connector_mgr.ingest_batch(batch) if records else {"run_id": connector_run_id, "records_staged": 0}

        sync_result = None
        if records and metadata.get("auto_sync") and connector_mgr.ontology_service is not None:
            sync_result = connector_mgr.sync_to_ontology(connector_name, run_id=connector_run_id)

        connector_mgr.store.complete_run(
            connector_run_id,
            status="completed",
            records_captured=len(records),
            records_synced=(sync_result or {}).get("synced", 0),
        )
        return {
            "message": "capture ingested",
            "ingest": ingest,
            "sync": sync_result,
            "records": len(records),
        }

    return on_complete


def build_browser_manager(connector_mgr: ConnectorManager, db_path: str | Path) -> BrowserActionManager:
    bridge = build_browser_bridge(db_path, on_complete=_build_ingest_handler(connector_mgr))
    return BrowserActionManager(connector_mgr, bridge)
