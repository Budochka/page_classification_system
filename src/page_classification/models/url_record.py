"""URL record and processing state models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProcessingState(str, Enum):
    """Processing states for each URL. All state transitions controlled by MCP Agent."""

    DISCOVERED = "DISCOVERED"
    FETCHED = "FETCHED"
    RENDERED = "RENDERED"
    EXTRACTED = "EXTRACTED"
    CLASSIFIED = "CLASSIFIED"
    VALIDATED = "VALIDATED"
    STORED = "STORED"  # terminal
    FAILED = "FAILED"  # terminal
    SKIPPED = "SKIPPED"  # terminal


# Terminal states - no further transitions
TERMINAL_STATES = {ProcessingState.STORED, ProcessingState.FAILED, ProcessingState.SKIPPED}


class URLRecord(BaseModel):
    """Record for a discovered URL from crawl."""

    url: str = Field(..., description="Normalized URL")
    discovered_from: Optional[str] = Field(None, description="URL or sitemap source")
    depth: int = Field(0, description="Crawl depth from start URLs")
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    state: ProcessingState = Field(default=ProcessingState.DISCOVERED)
    final_url: Optional[str] = None
    http_status: Optional[int] = None
    error: Optional[str] = None
