"""MCP Agent - control plane for page classification pipeline."""

import logging
from datetime import datetime
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential

from ..config.loader import Config, load_config
from ..models.url_record import URLRecord, ProcessingState, TERMINAL_STATES
from ..models.page_package import PagePackage
from ..models.classification_result import (
    ClassificationResult,
    StoredClassification,
)
from ..tools.crawl_tool import crawl_tool
from ..tools.fetch_tool import fetch_tool
from ..tools.render_tool import render_tool
from ..tools.extract_tool import extract_tool
from ..tools.classify_llm_tool import classify_llm_tool
from ..tools.validate_tool import validate_tool, apply_validation_fixes
from ..tools.storage_tool import storage_tool, storage_tool_sqlite

logger = logging.getLogger(__name__)


class MCPAgent:
    """
    MCP Agent orchestrates the page classification pipeline.
    Manages page lifecycle, invokes tools in order, enforces policies.
    Does NOT parse HTML, interpret semantics, or apply business rules directly.
    """

    def __init__(self, config: Config):
        self.config = config
        self.ruleset_version = self._get_ruleset_version()
        self.model_version = config.llm_provider_config.model

    def _get_ruleset_version(self) -> str:
        """Get ruleset version from file mtime or content hash."""
        p = Path(self.config.ruleset_path)
        if p.exists():
            return str(int(p.stat().st_mtime))
        return "0"

    def run(self) -> list[StoredClassification]:
        """Run full pipeline: crawl → fetch → extract → classify → validate → store."""
        # Initialize storage - clear existing results file to start fresh
        from ..tools.storage_tool import init_storage
        from pathlib import Path
        out_config = self.config.output_config
        storage_path = out_config.storage_path
        init_storage(storage_path, out_config.export_format or "jsonl")
        
        # Ensure output directory exists (init_storage creates parent, but ensure it's there)
        Path(storage_path).parent.mkdir(parents=True, exist_ok=True)
        
        records = crawl_tool(self.config)
        logger.info("Crawled %d URLs", len(records))

        stored: list[StoredClassification] = []
        for rec in records:
            try:
                result = self._process_url(rec)
                if result:
                    stored.append(result)
            except Exception as e:
                logger.exception("Failed URL %s: %s", rec.url, e)
                # Mark as FAILED, no storage

        logger.info("Successfully processed %d pages. Results saved to %s", len(stored), storage_path)
        return stored

    def _process_url(self, rec: URLRecord) -> StoredClassification | None:
        """Process single URL through pipeline."""
        if rec.state in TERMINAL_STATES:
            return None

        # Fetch
        fetch_result = self._fetch_with_retry(rec.url)
        if fetch_result.error or fetch_result.http_status not in (200,):
            if fetch_result.http_status in (404, 410, 403):
                return None  # SKIPPED
            logger.warning("Fetch failed %s: %s", rec.url, fetch_result.error)
            return None  # FAILED

        html = fetch_result.html
        final_url = fetch_result.final_url
        http_status = fetch_result.http_status
        content_type = fetch_result.content_type
        fetch_mode = "http"

        # Render policy: if sparse content or SPA markers, render
        render_policy = self.config.render_policy
        needs_render = (
            render_policy.force_render
            or len(html) < render_policy.min_text_chars
            or any(m in html for m in render_policy.spa_markers)
        )
        if needs_render:
            render_result = render_tool(final_url)
            if not render_result.error and render_result.html:
                html = render_result.html
                final_url = render_result.final_url
                fetch_mode = "render"

        # Extract
        page_package = extract_tool(
            url=rec.url,
            html=html,
            final_url=final_url,
            http_status=http_status,
            fetch_mode=fetch_mode,
            content_type=content_type,
            config=self.config,
        )

        # Classify
        classification = classify_llm_tool(page_package, self.config)

        # Validate
        valid, errors = validate_tool(classification, self.config.ruleset_path)
        if not valid:
            classification = apply_validation_fixes(classification)
            logger.debug("Validation fixes applied for %s: %s", rec.url, errors)

        # Build stored result
        stored = StoredClassification(
            url=rec.url,
            final_url=final_url,
            http_status=http_status,
            label=classification.label,
            confidence=classification.confidence,
            matched_rules=classification.matched_rules,
            rationale=classification.rationale,
            evidence=classification.evidence,
            needs_review=classification.needs_review,
            ruleset_version=self.ruleset_version,
            model_version=self.model_version,
            processed_at=datetime.utcnow(),
            fetch_mode=fetch_mode,
            content_hash=page_package.content_hash,
        )

        # Store
        out_config = self.config.output_config
        storage_path = out_config.storage_path
        if storage_path.endswith(".db"):
            storage_tool_sqlite(stored, storage_path)
        else:
            storage_tool(stored, storage_path, out_config.export_format or "jsonl")

        return stored

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_with_retry(self, url: str):
        """Fetch with retry for transient failures."""
        return fetch_tool(url, timeout=30)
