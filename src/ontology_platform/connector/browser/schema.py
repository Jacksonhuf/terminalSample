"""Browser Action Adapter protocol — generic Chrome Extension ↔ Platform."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

BrowserDriveMode = Literal["agent_loop", "scripted"]
BrowserCommandAction = Literal[
    "goto",
    "click",
    "fill",
    "select",
    "extract",
    "scroll",
    "wait",
    "snapshot",
    "finish",
    "noop",
]


class BrowserScriptStep(BaseModel):
    """Declarative step executed by the generic extension."""

    action: BrowserCommandAction
    selector: str = ""
    url: str = ""
    text: str = ""
    value: str = ""
    field: str = ""
    record_type: str = ""
    external_id: str = ""
    ms: int = 2000
    index: int = -1


class BrowserActionDef(BaseModel):
    """Named browser capability (maps to Ontology Action or capture profile)."""

    name: str
    display_name: str = ""
    description: str = ""
    steps: list[BrowserScriptStep] = Field(default_factory=list)


class BrowserProfile(BaseModel):
    """Extension matching and drive settings."""

    url_patterns: list[str] = Field(default_factory=lambda: ["http://*/*", "https://*/*"])
    drive_mode: BrowserDriveMode = "scripted"


class BrowserRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PageElement(BaseModel):
    index: int
    tag: str = ""
    type: str = ""
    text: str = ""
    id: str = ""
    name: str = ""
    selector: str = ""


class PageTable(BaseModel):
    index: int
    rows: list[list[str]] = Field(default_factory=list)


class PageState(BaseModel):
    url: str = ""
    title: str = ""
    elements: list[PageElement] = Field(default_factory=list)
    tables: list[PageTable] = Field(default_factory=list)
    extracted: dict[str, Any] = Field(default_factory=dict)


class BrowserCommand(BaseModel):
    """Instruction from platform to extension."""

    action: BrowserCommandAction
    selector: str = ""
    url: str = ""
    text: str = ""
    value: str = ""
    index: int = -1
    ms: int = 2000
    field: str = ""
    record_type: str = ""
    external_id: str = ""
    message: str = ""


class BrowserStepRequest(BaseModel):
    """Extension reports progress and requests next command."""

    page_state: PageState | None = None
    step_result: dict[str, Any] = Field(default_factory=dict)
    records: list[dict[str, Any]] = Field(default_factory=list)
    error: str = ""


class BrowserStepResponse(BaseModel):
    run_id: str
    status: BrowserRunStatus
    command: BrowserCommand | None = None
    done: bool = False
    message: str = ""


class CreateBrowserRunRequest(BaseModel):
    connector: str = ""
    drive_mode: BrowserDriveMode | None = None
    action_name: str = ""
    source_url: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    auto_sync: bool = True


class BrowserRunPublic(BaseModel):
    id: str
    connector_name: str
    status: BrowserRunStatus
    drive_mode: BrowserDriveMode
    action_name: str = ""
    source_url: str = ""
    connector_run_id: str = ""
    step_index: int = 0
    step_total: int = 0
    records_captured: int = 0
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
