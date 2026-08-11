"""FastAPI router for generic Browser Adapter v1 API."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from ontology_platform.browser_adapter.bridge import BrowserBridge
from ontology_platform.browser_adapter.schema import (
    CreateSessionRequest,
    SendCommandRequest,
    StepSubmitRequest,
)


def build_browser_router(bridge: BrowserBridge) -> APIRouter:
    router = APIRouter(prefix="/v1/browser", tags=["browser-adapter"])

    @router.post("/sessions")
    def create_session(body: CreateSessionRequest = Body()):
        try:
            return bridge.create_session(body)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @router.get("/sessions/pending")
    def list_pending_sessions(limit: int = 20):
        sessions = bridge.list_pending(limit)
        return {"sessions": sessions, "count": len(sessions)}

    @router.get("/sessions/{session_id}")
    def get_session(session_id: str):
        session = bridge.get_session(session_id)
        if session is None:
            raise HTTPException(404, f"Session not found: {session_id}")
        return session

    @router.delete("/sessions/{session_id}")
    def cancel_session(session_id: str):
        if not bridge.cancel_session(session_id):
            raise HTTPException(404, f"Session not found or already finished: {session_id}")
        return {"ok": True, "session_id": session_id}

    @router.post("/sessions/{session_id}/heartbeat")
    def session_heartbeat(session_id: str):
        if bridge.get_session(session_id) is None:
            raise HTTPException(404, f"Session not found: {session_id}")
        bridge.heartbeat(session_id)
        return {"ok": True}

    @router.post("/sessions/{session_id}/steps")
    def session_step(session_id: str, body: StepSubmitRequest = Body(default_factory=StepSubmitRequest)):
        if bridge.get_session(session_id) is None:
            raise HTTPException(404, f"Session not found: {session_id}")
        result = bridge.process_step(session_id, body)
        return result.model_dump()

    @router.post("/sessions/{session_id}/commands")
    def send_command(session_id: str, body: SendCommandRequest = Body()):
        try:
            result = bridge.send_command(session_id, body)
            return result.model_dump()
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except TimeoutError as exc:
            raise HTTPException(408, str(exc))

    @router.get("/sessions/{session_id}/steps/wait")
    def wait_step(session_id: str, after_version: int = 0, timeout_sec: float = 30.0):
        if bridge.get_session(session_id) is None:
            raise HTTPException(404, f"Session not found: {session_id}")
        result = bridge.wait_step(session_id, after_version=after_version, timeout_sec=timeout_sec)
        if result is None:
            return {"ready": False, "step": None}
        return {"ready": True, "step": result.model_dump()}

    return router
