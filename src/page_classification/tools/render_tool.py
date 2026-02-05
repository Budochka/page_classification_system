"""Render tool - render SPA pages with headless browser."""

from dataclasses import dataclass


@dataclass
class RenderResult:
    """Result from render_tool."""

    html: str
    final_url: str
    error: str | None = None


def render_tool(url: str, timeout_ms: int = 15000) -> RenderResult:
    """
    Render page with Playwright (headless Chromium).
    Used when fetch yields insufficient content (SPA).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return RenderResult(
            html="",
            final_url=url,
            error="playwright not installed. Run: pip install playwright && playwright install chromium",
        )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            html = page.content()
            final_url = page.url
            browser.close()
            return RenderResult(html=html, final_url=final_url, error=None)
    except Exception as e:
        return RenderResult(html="", final_url=url, error=str(e))
