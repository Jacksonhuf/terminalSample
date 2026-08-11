"""Generic Browser Adapter protocol v1 — agent-agnostic session / command model."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ontology_platform.connector.browser.schema import (
    BrowserCommand,
    BrowserCommandAction,
    BrowserScriptStep,
    BrowserStepRequest,
    PageElement,
    PageState,
    PageTable,
)

SessionMode = Literal["interactive", "scripted", "async"]
SessionStatus = Literal[
    "pending",
    "running",
    "waiting_agent",
    "waiting_extension",
    "completed",
    "failed",
    "cancelled",
]
TabPolicy = Literal["reuse", "new", "active"]


class CreateSessionRequest(BaseModel):
    """Create a browser session — callable by any agent driver."""

    mode: SessionMode = "scripted"
    start_url: str = ""
    tab_policy: TabPolicy = "reuse"
    script: list[BrowserScriptStep] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    allowed_url_patterns: list[str] = Field(default_factory=list)


class SendCommandRequest(BaseModel):
    """Agent pushes a single command (interactive mode)."""

    command: BrowserCommand
    wait_timeout_sec: float = 30.0


class StepSubmitRequest(BaseModel):
    """Extension reports step outcome and requests next command."""

    command_id: str = ""
    page_state: PageState | None = None
    step_result: dict[str, Any] = Field(default_factory=dict)
    data: list[dict[str, Any]] = Field(default_factory=list)
    records: list[dict[str, Any]] = Field(default_factory=list)  # alias for data
    error: str = ""


class StepResponse(BaseModel):
    """Bridge → extension or agent step loop response."""

    session_id: str
    status: SessionStatus
    command: BrowserCommand | None = None
    command_id: str = ""
    done: bool = False
    message: str = ""
    step_index: int = 0
    step_total: int = 0


class StepResultPublic(BaseModel):
    """Last step result exposed to waiting agents."""

    session_id: str
    command_id: str = ""
    ok: bool = True
    page_state: PageState | None = None
    step_result: dict[str, Any] = Field(default_factory=dict)
    data: list[dict[str, Any]] = Field(default_factory=list)
    error: str = ""
    step_version: int = 0


class SessionPublic(BaseModel):
    id: str
    status: SessionStatus
    mode: SessionMode
    start_url: str = ""
    tab_policy: TabPolicy = "reuse"
    metadata: dict[str, Any] = Field(default_factory=dict)
    step_index: int = 0
    step_total: int = 0
    data_count: int = 0
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    last_step: StepResultPublic | None = None

    # Legacy / Ontology connector fields (from metadata)
    @property
    def connector_name(self) -> str:
        return str(self.metadata.get("connector_name", ""))

    @property
    def source_url(self) -> str:
        return self.start_url


__all__ = [
    "BrowserCommand",
    "BrowserCommandAction",
    "BrowserScriptStep",
    "CreateSessionRequest",
    "PageElement",
    "PageState",
    "PageTable",
    "SendCommandRequest",
    "SessionMode",
    "SessionPublic",
    "SessionStatus",
    "StepResponse",
    "StepResultPublic",
    "StepSubmitRequest",
    "TabPolicy",
]
