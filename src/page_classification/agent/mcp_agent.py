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
        
        # Track processed pages
        stored: list[StoredClassification] = []
        processed_urls: set[str] = set()  # Track which URLs have been processed
        processed_count = [0]  # Use list to allow modification in nested function
        
        def process_during_crawl(url: str, html: str, final_url: str, http_status: int, content_type: str) -> StoredClassification | None:
            """Process page immediately during crawling to avoid double-fetching."""
            # Skip if already processed
            if url in processed_urls:
                return None
                
            processed_count[0] += 1
            logger.info("[Processing during crawl] %s", url)
            
            try:
                # Create a temporary URLRecord for processing
                rec = URLRecord(
                    url=url,
                    discovered_from="crawl",
                    depth=0,
                    discovered_at=datetime.utcnow(),
                    state=ProcessingState.DISCOVERED,
                )
                
                # Process using existing logic (but skip fetch since we already have HTML)
                result = self._process_url_with_html(rec, html, final_url, http_status, content_type)
                if result:
                    stored.append(result)
                    processed_urls.add(url)  # Mark as processed
                    logger.info("Successfully processed %s during crawl", url)
                return result
            except Exception as e:
                logger.exception("Failed to process %s during crawl: %s", url, e)
                return None
        
        # Crawl with processing callback - pages are processed immediately when fetched
        records = crawl_tool(self.config, process_callback=process_during_crawl)
        logger.info("Crawled %d URLs, processed %d pages during crawl", len(records), processed_count[0])
        
        # Process any URLs that weren't processed during crawl (e.g., from sitemaps that weren't HTML)
        unprocessed = [rec for rec in records if rec.url not in processed_urls]
        if unprocessed:
            logger.info("Processing %d remaining URLs that weren't processed during crawl...", len(unprocessed))
            for idx, rec in enumerate(unprocessed, 1):
                try:
                    logger.info("[%d/%d] Processing %s", idx, len(unprocessed), rec.url)
                    result = self._process_url(rec)
                    if result:
                        stored.append(result)
                        logger.info("[%d/%d] Successfully processed %s", idx, len(unprocessed), rec.url)
                    else:
                        logger.info("[%d/%d] Skipped %s (returned None)", idx, len(unprocessed), rec.url)
                except Exception as e:
                    logger.exception("Failed URL %s: %s", rec.url, e)

        logger.info("Successfully processed %d pages total. Results saved to %s", len(stored), storage_path)
        return stored

    def _process_url(self, rec: URLRecord) -> StoredClassification | None:
        """Process single URL through pipeline (fetches the page)."""
        logger.debug("Processing URL: %s", rec.url)
        if rec.state in TERMINAL_STATES:
            logger.debug("Skipping %s: terminal state", rec.url)
            return None

        # Fetch
        fetch_result = self._fetch_with_retry(rec.url)
        if fetch_result.error or fetch_result.http_status not in (200,):
            if fetch_result.http_status in (404, 410, 403):
                logger.debug("Skipping %s: HTTP %s", rec.url, fetch_result.http_status)
                return None  # SKIPPED
            logger.warning("Fetch failed %s: %s", rec.url, fetch_result.error)
            return None  # FAILED
        
        logger.debug("Fetched %s successfully, status %s", rec.url, fetch_result.http_status)

        return self._process_url_with_html(
            rec, 
            fetch_result.html, 
            fetch_result.final_url, 
            fetch_result.http_status, 
            fetch_result.content_type
        )
    
    def _process_url_with_html(
        self, 
        rec: URLRecord, 
        html: str, 
        final_url: str, 
        http_status: int, 
        content_type: str
    ) -> StoredClassification | None:
        """Process URL with already-fetched HTML (shared logic for both crawl-time and post-crawl processing)."""
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
        logger.debug("Classifying %s", rec.url)
        classification = classify_llm_tool(page_package, self.config)
        logger.debug("Classified %s as %s", rec.url, classification.labels)

        # Validate
        valid, errors = validate_tool(classification, self.config.ruleset_path)
        if not valid:
            classification = apply_validation_fixes(classification)
            logger.debug("Validation fixes applied for %s: %s", rec.url, errors)

        # Build stored result
        logger.debug("Building stored result for %s", rec.url)
        stored = StoredClassification(
            url=rec.url,
            final_url=final_url,
            http_status=http_status,
            labels=classification.labels,
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
        logger.info("Storing result for %s to %s", rec.url, storage_path)
        try:
            if storage_path.endswith(".db"):
                storage_tool_sqlite(stored, storage_path)
            else:
                storage_tool(stored, storage_path, out_config.export_format or "jsonl")
            logger.info("Successfully stored result for %s", rec.url)
        except Exception as e:
            logger.error("Failed to store result for %s: %s", rec.url, e, exc_info=True)
            # Don't fail the whole process, but log the error
            raise  # Re-raise to be caught by outer try/except

        return stored

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_with_retry(self, url: str):
        """Fetch with retry for transient failures."""
        return fetch_tool(url, timeout=30)
