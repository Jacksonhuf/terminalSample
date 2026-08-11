"""Browser Action Adapter public API."""

from ontology_platform.connector.browser.schema import (
    BrowserCommand,
    BrowserRunPublic,
    BrowserStepRequest,
    BrowserStepResponse,
    CreateBrowserRunRequest,
    PageState,
)

__all__ = [
    "BrowserActionManager",
    "BrowserCommand",
    "BrowserRunPublic",
    "BrowserStepRequest",
    "BrowserStepResponse",
    "CreateBrowserRunRequest",
    "PageState",
    "build_browser_manager",
]


def __getattr__(name: str):
    if name == "BrowserActionManager":
        from ontology_platform.connector.browser.manager import BrowserActionManager

        return BrowserActionManager
    if name == "build_browser_manager":
        from ontology_platform.connector.browser.manager import build_browser_manager

        return build_browser_manager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
