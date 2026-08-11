"""Browser Action Adapter — orchestrates extension runs and capture ingest."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ontology_platform.connector.browser.schema import (
    BrowserCommand,
    BrowserDriveMode,
    BrowserRunStatus,
    BrowserStepRequest,
    BrowserStepResponse,
    BrowserScriptStep,
    CreateBrowserRunRequest,
)
from ontology_platform.connector.browser.step_engine import (
    merge_step_records,
    next_agent_loop_command,
    next_scripted_command,
)
from ontology_platform.connector.browser.store import BrowserRunStore
from ontology_platform.connector.manager import ConnectorManager
from ontology_platform.connector.schema import CaptureBatch, CaptureMode, CaptureRecord, ConnectorDef


class BrowserActionManager:
    """Generic browser adapter: task queue + step engine + capture ingest."""

    def __init__(
        self,
        connector_mgr: ConnectorManager,
        browser_store: BrowserRunStore,
    ) -> None:
        self.connector_mgr = connector_mgr
        self.browser_store = browser_store

    def create_run(self, req: CreateBrowserRunRequest) -> dict[str, Any]:
        connector = self.connector_mgr.load_connector(req.connector)
        if connector.mode not in (CaptureMode.BROWSER_EXTENSION, CaptureMode.COMPUTER_USE):
            # allow starting browser run for any connector with browser_profile
            pass

        drive_mode: BrowserDriveMode = req.drive_mode or self._default_drive_mode(connector)
        source_url = req.source_url or connector.source_url
        steps, action_name = self._resolve_steps(connector, req.action_name, req.parameters)

        run = self.browser_store.create_run(
            connector_name=connector.name,
            drive_mode=drive_mode,
            action_name=action_name or req.action_name,
            source_url=source_url,
            steps=steps,
            parameters=req.parameters,
            auto_sync=req.auto_sync,
        )

        initial = self._initial_command(run.id)
        return {
            "run": run.model_dump(),
            "initial_command": initial.model_dump() if initial else None,
        }

    def list_pending(self, limit: int = 20) -> list[dict[str, Any]]:
        return [r.model_dump() for r in self.browser_store.list_pending(limit)]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = self.browser_store.get_run(run_id)
        return run.model_dump() if run else None

    def heartbeat(self, run_id: str) -> None:
        self.browser_store.heartbeat(run_id)

    def process_step(self, run_id: str, body: BrowserStepRequest) -> BrowserStepResponse:
        row = self.browser_store.get_run_row(run_id)
        if row is None:
            return BrowserStepResponse(
                run_id=run_id,
                status=BrowserRunStatus.FAILED,
                done=True,
                message="run not found",
            )

        if body.error:
            self._fail_run(run_id, body.error)
            return BrowserStepResponse(
                run_id=run_id,
                status=BrowserRunStatus.FAILED,
                done=True,
                message=body.error,
            )

        status = BrowserRunStatus(row["status"])
        if status in (BrowserRunStatus.COMPLETED, BrowserRunStatus.FAILED):
            return BrowserStepResponse(
                run_id=run_id,
                status=status,
                done=True,
                message="run already finished",
            )

        if status == BrowserRunStatus.PENDING:
            self.browser_store.update_run(run_id, status=BrowserRunStatus.RUNNING.value)

        collected = json.loads(row["collected_records_json"] or "[]")
        collected = merge_step_records(collected, body, body.page_state)
        self.browser_store.update_run(
            run_id,
            collected_records_json=json.dumps(collected, ensure_ascii=False),
        )

        connector = self.connector_mgr.load_connector(row["connector_name"])
        ctx = {
            **json.loads(row["parameters_json"] or "{}"),
            "source_url": row["source_url"] or connector.source_url,
        }

        drive_mode: BrowserDriveMode = row["drive_mode"]  # type: ignore[assignment]
        step_index = row["step_index"]
        steps = json.loads(row["steps_json"] or "[]")

        cmd: BrowserCommand | None = None
        done = False
        message = ""

        if body.records or (body.step_result.get("action") == "finish"):
            done = True
            message = "extension finished"
        elif drive_mode == "scripted" and steps:
            cmd, step_index, done = next_scripted_command(steps, step_index, ctx)
        else:
            expected = [m.record_type for m in connector.record_mappings]
            cmd, step_index, done = next_agent_loop_command(
                page_state=body.page_state,
                step_index=step_index,
                source_url=row["source_url"] or connector.source_url,
                instructions=connector.capture_instructions,
                expected_record_types=expected,
            )

        self.browser_store.update_run(run_id, step_index=step_index)

        if done or (cmd and cmd.action == "finish"):
            ingest_result = self._complete_run(run_id, row, collected, connector)
            return BrowserStepResponse(
                run_id=run_id,
                status=BrowserRunStatus.COMPLETED,
                command=cmd,
                done=True,
                message=ingest_result.get("message", message or "completed"),
            )

        return BrowserStepResponse(
            run_id=run_id,
            status=BrowserRunStatus.RUNNING,
            command=cmd,
            done=False,
            message=message,
        )

    def _initial_command(self, run_id: str) -> BrowserCommand | None:
        row = self.browser_store.get_run_row(run_id)
        if row is None:
            return None
        connector = self.connector_mgr.load_connector(row["connector_name"])
        ctx = {
            **json.loads(row["parameters_json"] or "{}"),
            "source_url": row["source_url"] or connector.source_url,
        }
        steps = json.loads(row["steps_json"] or "[]")
        drive_mode: BrowserDriveMode = row["drive_mode"]  # type: ignore[assignment]

        if drive_mode == "scripted" and steps:
            cmd, _, _ = next_scripted_command(steps, 0, ctx)
            return cmd
        if row["source_url"] or connector.source_url:
            return BrowserCommand(action="goto", url=row["source_url"] or connector.source_url)
        return BrowserCommand(action="snapshot")

    def _complete_run(
        self,
        run_id: str,
        row: dict[str, Any],
        collected: list[dict[str, Any]],
        connector: ConnectorDef,
    ) -> dict[str, Any]:
        records = []
        for item in collected:
            records.append(
                CaptureRecord(
                    record_type=item.get("record_type", "record"),
                    external_id=str(item.get("external_id", "unknown")),
                    payload=item.get("payload") or item,
                )
            )

        connector_run_id = row.get("connector_run_id") or self.connector_mgr.start_run(connector.name)
        batch = CaptureBatch(
            connector=connector.name,
            run_id=connector_run_id,
            source_url=row.get("source_url") or connector.source_url,
            records=records,
        )
        ingest = self.connector_mgr.ingest_batch(batch) if records else {"run_id": connector_run_id, "records_staged": 0}

        sync_result = None
        if records and row.get("auto_sync") and self.connector_mgr.ontology_service is not None:
            sync_result = self.connector_mgr.sync_to_ontology(connector.name, run_id=connector_run_id)

        self.browser_store.update_run(
            run_id,
            status=BrowserRunStatus.COMPLETED.value,
            connector_run_id=connector_run_id,
            records_captured=len(records),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        self.connector_mgr.store.complete_run(
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

    def _fail_run(self, run_id: str, error: str) -> None:
        self.browser_store.update_run(
            run_id,
            status=BrowserRunStatus.FAILED.value,
            error=error,
            finished_at=datetime.now(timezone.utc).isoformat(),
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


def build_browser_manager(connector_mgr: ConnectorManager, db_path: str | Path) -> BrowserActionManager:
    return BrowserActionManager(connector_mgr, BrowserRunStore(db_path))
