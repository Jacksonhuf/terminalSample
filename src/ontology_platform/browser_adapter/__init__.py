"""Generic Browser Action Adapter — agent-agnostic bridge for Chrome Extension."""

from ontology_platform.browser_adapter.bridge import BrowserBridge, build_browser_bridge
from ontology_platform.browser_adapter.schema import (
    BrowserCommand,
    CreateSessionRequest,
    PageState,
    SessionMode,
    SessionPublic,
    SessionStatus,
    StepResponse,
    StepSubmitRequest,
)
from ontology_platform.browser_adapter.sdk import BrowserAdapterClient

__all__ = [
    "BrowserAdapterClient",
    "BrowserBridge",
    "BrowserCommand",
    "CreateSessionRequest",
    "PageState",
    "SessionMode",
    "SessionPublic",
    "SessionStatus",
    "StepResponse",
    "StepSubmitRequest",
    "build_browser_bridge",
]
