"""Fetch tool - retrieve HTML via HTTP."""

from dataclasses import dataclass

import httpx


@dataclass
class FetchResult:
    """Result from fetch_tool."""

    final_url: str
    http_status: int
    content_type: str
    html: str
    error: str | None = None


def fetch_tool(url: str, timeout: int = 30) -> FetchResult:
    """
    Fetch HTML from URL.
    Returns final_url, http_status, content_type, html, error.
    """
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
            response = client.get(url)
            return FetchResult(
                final_url=str(response.url),
                http_status=response.status_code,
                content_type=response.headers.get("content-type", "application/octet-stream"),
                html=response.text,
                error=None,
            )
    except Exception as e:
        return FetchResult(
            final_url=url,
            http_status=0,
            content_type="",
            html="",
            error=str(e),
        )
