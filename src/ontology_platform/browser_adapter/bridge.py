"""Browser Bridge — session orchestration for extension and external agents."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ontology_platform.browser_adapter.schema import (
    BrowserCommand,
    CreateSessionRequest,
    PageState,
    SendCommandRequest,
    SessionPublic,
    SessionStatus,
    StepResponse,
    StepResultPublic,
    StepSubmitRequest,
)
from ontology_platform.browser_adapter.store import BrowserSessionStore
from ontology_platform.connector.browser.step_engine import merge_step_records, next_scripted_command


CompletionHandler = Callable[[str, dict[str, Any], list[dict[str, Any]]], dict[str, Any] | None]


class BrowserBridge:
    """Generic bridge: extension executor + optional agent command queue."""

    def __init__(
        self,
        store: BrowserSessionStore,
        on_complete: CompletionHandler | None = None,
    ) -> None:
        self.store = store
        self._on_complete = on_complete
        self._step_events: dict[str, threading.Event] = {}
        self._step_lock = threading.Lock()

    def create_session(self, req: CreateSessionRequest) -> dict[str, Any]:
        steps = [s.model_dump() for s in req.script]
        ctx = {**req.parameters, "start_url": req.start_url}
        session = self.store.create_session(
            mode=req.mode,
            start_url=req.start_url,
            tab_policy=req.tab_policy,
            metadata=req.metadata,
            steps=steps,
            parameters=ctx,
        )
        initial = self._peek_initial_command(session.id)
        return {
            "session": session.model_dump(),
            "initial_command": initial.model_dump() if initial else None,
        }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        session = self.store.get_session(session_id)
        return session.model_dump() if session else None

    def list_pending(self, limit: int = 20) -> list[dict[str, Any]]:
        return [s.model_dump() for s in self.store.list_pending(limit)]

    def cancel_session(self, session_id: str) -> bool:
        row = self.store.get_row(session_id)
        if row is None:
            return False
        if row["status"] in ("completed", "failed", "cancelled"):
            return False
        self.store.update_session(
            session_id,
            status="cancelled",
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        self._notify_step(session_id)
        return True

    def heartbeat(self, session_id: str) -> None:
        self.store.heartbeat(session_id)

    def send_command(self, session_id: str, req: SendCommandRequest) -> StepResultPublic:
        """Interactive mode: agent queues command and waits for extension result."""
        row = self.store.get_row(session_id)
        if row is None:
            raise ValueError(f"session not found: {session_id}")
        if row["mode"] != "interactive":
            raise ValueError("send_command only supported for interactive sessions")
        if row["status"] in ("completed", "failed", "cancelled"):
            raise ValueError(f"session already {row['status']}")

        cmd_id = str(uuid.uuid4())
        with self._step_lock:
            start_version = row["step_version"]
            event = self._step_events.setdefault(session_id, threading.Event())
            event.clear()
            self.store.update_session(
                session_id,
                status="waiting_extension",
                pending_command_json=json.dumps(req.command.model_dump(), ensure_ascii=False),
                pending_command_id=cmd_id,
            )

        if not event.wait(timeout=max(1.0, req.wait_timeout_sec)):
            raise TimeoutError(f"extension did not complete command within {req.wait_timeout_sec}s")

        row = self.store.get_row(session_id)
        if row is None:
            raise ValueError("session disappeared")
        if row["last_step_json"]:
            result = StepResultPublic.model_validate(json.loads(row["last_step_json"]))
            if result.command_id == cmd_id:
                return result
        if row["step_version"] > start_version and row["last_step_json"]:
            return StepResultPublic.model_validate(json.loads(row["last_step_json"]))
        raise TimeoutError("step result not available")

    def wait_step(self, session_id: str, after_version: int = 0, timeout_sec: float = 30.0) -> StepResultPublic | None:
        """Poll until step_version increases (non-blocking alternative to send_command wait)."""
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            row = self.store.get_row(session_id)
            if row is None:
                return None
            if row["step_version"] > after_version and row["last_step_json"]:
                return StepResultPublic.model_validate(json.loads(row["last_step_json"]))
            event = self._step_events.setdefault(session_id, threading.Event())
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            event.wait(timeout=min(1.0, remaining))
            event.clear()
        return None

    def process_step(self, session_id: str, body: StepSubmitRequest) -> StepResponse:
        row = self.store.get_row(session_id)
        if row is None:
            return StepResponse(
                session_id=session_id,
                status="failed",
                done=True,
                message="session not found",
            )

        if body.error:
            self._fail_session(session_id, body.error)
            return StepResponse(session_id=session_id, status="failed", done=True, message=body.error)

        status: SessionStatus = row["status"]  # type: ignore[assignment]
        if status in ("completed", "failed", "cancelled"):
            return StepResponse(
                session_id=session_id,
                status=status,
                done=True,
                message="session already finished",
            )

        if status == "pending":
            self.store.update_session(session_id, status="running")

        # Normalize data / records
        incoming_data = list(body.data) or list(body.records)
        collected = json.loads(row["collected_data_json"] or "[]")
        collected = self._merge_data(collected, body, incoming_data)
        self.store.update_session(
            session_id,
            collected_data_json=json.dumps(collected, ensure_ascii=False),
        )

        mode = row["mode"]
        step_index = row["step_index"]
        steps = json.loads(row["steps_json"] or "[]")
        ctx = json.loads(row["parameters_json"] or "{}")

        cmd: BrowserCommand | None = None
        cmd_id = ""
        done = False
        message = ""

        finish_requested = (
            incoming_data
            or body.step_result.get("action") == "finish"
            or (body.page_state and body.page_state.extracted.get("_finish"))
        )

        if mode == "interactive":
            pending_json = row.get("pending_command_json")
            has_result = bool(
                body.page_state
                or body.step_result
                or incoming_data
                or body.error
            )
            if pending_json and not has_result:
                cmd = BrowserCommand.model_validate(json.loads(pending_json))
                return StepResponse(
                    session_id=session_id,
                    status="waiting_extension",
                    command=cmd,
                    command_id=row["pending_command_id"] or "",
                    done=False,
                    step_index=step_index,
                    step_total=row["step_total"],
                )
            if has_result or finish_requested:
                cmd, cmd_id, done, message = self._interactive_step(
                    session_id, row, body, incoming_data, finish_requested
                )
            else:
                self.store.update_session(session_id, status="waiting_agent")
                return StepResponse(
                    session_id=session_id,
                    status="waiting_agent",
                    done=False,
                    message="awaiting agent command via POST /commands",
                    step_index=step_index,
                    step_total=row["step_total"],
                )
        elif mode == "scripted" and steps:
            if finish_requested:
                done = True
                message = "extension finished"
            else:
                cmd, step_index, done = next_scripted_command(steps, step_index, ctx)
                if done or (cmd and cmd.action == "finish"):
                    done = True
            self.store.update_session(session_id, step_index=step_index)
        else:
            # async / agent_loop placeholder: goto → snapshot → wait for agent commands
            if finish_requested:
                done = True
            elif row["pending_command_json"]:
                cmd = BrowserCommand.model_validate(json.loads(row["pending_command_json"]))
                cmd_id = row["pending_command_id"] or ""
                self.store.update_session(
                    session_id,
                    pending_command_json=None,
                    pending_command_id=None,
                    status="running",
                )
            elif step_index == 0 and row["start_url"]:
                cmd = BrowserCommand(action="goto", url=row["start_url"])
                step_index = 1
                self.store.update_session(session_id, step_index=step_index)
            else:
                self.store.update_session(session_id, status="waiting_agent")
                return StepResponse(
                    session_id=session_id,
                    status="waiting_agent",
                    done=False,
                    message="awaiting agent command via POST /commands",
                    step_index=step_index,
                    step_total=row["step_total"],
                )

        if done:
            complete_msg = self._complete_session(session_id, row, collected)
            return StepResponse(
                session_id=session_id,
                status="completed",
                command=cmd,
                command_id=cmd_id,
                done=True,
                message=complete_msg,
                step_index=step_index,
                step_total=row["step_total"],
            )

        return StepResponse(
            session_id=session_id,
            status="running" if mode != "interactive" else "waiting_agent",
            command=cmd,
            command_id=cmd_id,
            done=False,
            message=message,
            step_index=step_index,
            step_total=row["step_total"],
        )

    def _interactive_step(
        self,
        session_id: str,
        row: dict[str, Any],
        body: StepSubmitRequest,
        incoming_data: list[dict[str, Any]],
        finish_requested: bool,
    ) -> tuple[BrowserCommand | None, str, bool, str]:
        pending_id = row["pending_command_id"] or body.command_id or ""
        step_version = row["step_version"] + 1
        step_result = StepResultPublic(
            session_id=session_id,
            command_id=pending_id,
            ok=not body.error,
            page_state=body.page_state,
            step_result=body.step_result,
            data=incoming_data,
            error=body.error,
            step_version=step_version,
        )
        self.store.update_session(
            session_id,
            last_step_json=json.dumps(step_result.model_dump(), ensure_ascii=False),
            step_version=step_version,
            status="waiting_agent" if not finish_requested else "running",
            pending_command_json=None,
            pending_command_id=None,
        )
        self._notify_step(session_id)

        if finish_requested:
            return None, pending_id, True, "session finish requested"

        pending = row.get("pending_command_json")
        if pending:
            cmd = BrowserCommand.model_validate(json.loads(pending))
            return cmd, row["pending_command_id"] or "", False, ""

        return None, pending_id, False, "awaiting next agent command"

    def _peek_initial_command(self, session_id: str) -> BrowserCommand | None:
        row = self.store.get_row(session_id)
        if row is None:
            return None
        steps = json.loads(row["steps_json"] or "[]")
        ctx = json.loads(row["parameters_json"] or "{}")
        if row["mode"] == "scripted" and steps:
            cmd, _, _ = next_scripted_command(steps, 0, ctx)
            return cmd
        if row["start_url"]:
            return BrowserCommand(action="goto", url=row["start_url"])
        return BrowserCommand(action="snapshot")

    def _merge_data(
        self,
        existing: list[dict[str, Any]],
        body: StepSubmitRequest,
        incoming_data: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        from ontology_platform.connector.browser.schema import BrowserStepRequest

        legacy = BrowserStepRequest(
            page_state=body.page_state,
            step_result=body.step_result,
            records=incoming_data,
            error=body.error,
        )
        return merge_step_records(existing, legacy, body.page_state)

    def _complete_session(
        self,
        session_id: str,
        row: dict[str, Any],
        collected: list[dict[str, Any]],
    ) -> str:
        metadata = json.loads(row["metadata_json"] or "{}")
        result: dict[str, Any] = {"records": len(collected), "data": collected}
        if self._on_complete:
            try:
                hook_result = self._on_complete(session_id, metadata, collected)
                if hook_result:
                    result.update(hook_result)
                    ingest = hook_result.get("ingest") or {}
                    if ingest.get("run_id"):
                        metadata["connector_run_id"] = ingest["run_id"]
                    sync = hook_result.get("sync") or {}
                    metadata["completion"] = {
                        "message": hook_result.get("message", ""),
                        "records_captured": hook_result.get("records", len(collected)),
                        "records_synced": sync.get("synced", 0),
                        "ingest": ingest,
                        "sync": sync,
                    }
            except Exception as exc:
                self._fail_session(session_id, str(exc))
                return str(exc)

        self.store.update_session(
            session_id,
            status="completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        self._notify_step(session_id)
        return result.get("message", "completed")

    def _fail_session(self, session_id: str, error: str) -> None:
        self.store.update_session(
            session_id,
            status="failed",
            error=error,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        self._notify_step(session_id)

    def _notify_step(self, session_id: str) -> None:
        event = self._step_events.get(session_id)
        if event:
            event.set()


def build_browser_bridge(db_path: str | Path, on_complete: CompletionHandler | None = None) -> BrowserBridge:
    return BrowserBridge(BrowserSessionStore(db_path), on_complete=on_complete)
