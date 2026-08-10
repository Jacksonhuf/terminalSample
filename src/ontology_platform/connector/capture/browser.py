"""Playwright browser helpers for LLM Computer Use (optional dependency)."""

from __future__ import annotations

import base64
from typing import Any

PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import Browser, Page, Playwright, sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    Browser = Page = Playwright = None  # type: ignore[misc, assignment]
    sync_playwright = None  # type: ignore[assignment]


class BrowserSession:
    """Thin wrapper around a headless Chromium session."""

    def __init__(self, headless: bool = True) -> None:
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "playwright 未安装。请执行: pip install -e \".[capture]\" && playwright install chromium"
            )
        self._headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self.page: Page | None = None

    def __enter__(self) -> BrowserSession:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        self.page = self._browser.new_page()
        self.page.set_default_timeout(30000)
        return self

    def __exit__(self, *args: object) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def goto(self, url: str) -> None:
        assert self.page is not None
        self.page.goto(url, wait_until="domcontentloaded")

    def screenshot_base64(self) -> str:
        assert self.page is not None
        data = self.page.screenshot(type="png", full_page=False)
        return base64.b64encode(data).decode("ascii")

    def page_snapshot(self) -> dict[str, Any]:
        assert self.page is not None
        elements = self.page.evaluate(
            """() => {
              const items = [];
              const nodes = document.querySelectorAll(
                'a, button, input, select, textarea, [role=button], [role=link]'
              );
              nodes.forEach((el, i) => {
                if (i >= 100) return;
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) return;
                const text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim();
                items.push({
                  index: i,
                  tag: el.tagName.toLowerCase(),
                  type: el.type || '',
                  text: text.slice(0, 120),
                  id: el.id || '',
                  name: el.name || '',
                });
              });
              const tables = [];
              document.querySelectorAll('table').forEach((table, ti) => {
                if (ti >= 3) return;
                const rows = [];
                table.querySelectorAll('tr').forEach((tr, ri) => {
                  if (ri >= 15) return;
                  const cells = Array.from(tr.querySelectorAll('th,td')).map(c => c.innerText.trim().slice(0, 80));
                  if (cells.some(Boolean)) rows.push(cells);
                });
                if (rows.length) tables.push({ index: ti, rows });
              });
              return {
                url: location.href,
                title: document.title,
                elements: items,
                tables,
              };
            }"""
        )
        return elements

    def click_index(self, index: int) -> None:
        assert self.page is not None
        self.page.evaluate(
            """(idx) => {
              const nodes = document.querySelectorAll(
                'a, button, input, select, textarea, [role=button], [role=link]'
              );
              const el = nodes[idx];
              if (el) el.click();
            }""",
            index,
        )

    def type_index(self, index: int, text: str) -> None:
        assert self.page is not None
        self.page.evaluate(
            """({ idx, text }) => {
              const nodes = document.querySelectorAll(
                'a, button, input, select, textarea, [role=button], [role=link]'
              );
              const el = nodes[idx];
              if (!el) return;
              if ('value' in el) {
                el.value = text;
                el.dispatchEvent(new Event('input', { bubbles: true }));
              }
            }""",
            {"idx": index, "text": text},
        )

    def scroll_down(self) -> None:
        assert self.page is not None
        self.page.evaluate("() => window.scrollBy(0, window.innerHeight * 0.8)")

    def wait_short(self) -> None:
        assert self.page is not None
        self.page.wait_for_timeout(2000)
