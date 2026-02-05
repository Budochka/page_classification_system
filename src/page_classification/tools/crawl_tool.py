"""Crawl tool - collect URLs from sitemap and internal links."""

from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..config.loader import Config
from ..models.url_record import URLRecord, ProcessingState


def normalize_url(
    url: str,
    base: str | None = None,
    rules: dict | None = None,
) -> str:
    """Normalize URL: strip fragments, sort query, lowercase scheme/host."""
    parsed = urlparse(url)
    if base and not parsed.netloc:
        url = urljoin(base, url)
        parsed = urlparse(url)

    # Strip fragment
    result = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if parsed.query:
        result += "?" + parsed.query
    return result.rstrip("/") or result + "/"


def crawl_tool(
    config: Config,
    start_urls: list[str] | None = None,
) -> list[URLRecord]:
    """
    Collect URLs from sitemap.xml and internal links.
    Normalize, deduplicate, enforce domain and depth limits.
    """
    start_urls = start_urls or config.start_urls
    if not start_urls:
        return []
    allowed = set(config.allowed_domains) if config.allowed_domains else None
    if not allowed:
        allowed = {urlparse(u).netloc for u in start_urls}
    limits = config.crawl_limits
    rules = config.url_normalization_rules

    seen: set[str] = set()
    records: list[URLRecord] = []
    queue: list[tuple[str, str | None, int]] = []

    for u in start_urls:
        norm = normalize_url(u, rules=rules)
        if norm not in seen:
            seen.add(norm)
            queue.append((norm, None, 0))

    # Try sitemap first - handle both regular sitemaps and sitemap indexes
    sitemap_urls_to_process: list[str] = []
    for base_url in start_urls:
        parsed = urlparse(base_url)
        sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
        sitemap_urls_to_process.append(sitemap_url)
    
    # Process sitemaps (including following sitemap indexes)
    processed_sitemaps: set[str] = set()
    with httpx.Client(timeout=30, follow_redirects=True, trust_env=False) as client:
        while sitemap_urls_to_process and len(records) < limits.max_pages:
            sitemap_url = sitemap_urls_to_process.pop(0)
            if sitemap_url in processed_sitemaps:
                continue
            processed_sitemaps.add(sitemap_url)
            
            try:
                r = client.get(sitemap_url)
                if r.status_code != 200 or "xml" not in r.headers.get("content-type", ""):
                    continue
                
                soup = BeautifulSoup(r.text, "xml")
                
                # Check if this is a sitemap index (has <sitemap> tags)
                sitemap_tags = soup.find_all("sitemap")
                if sitemap_tags:
                    # This is a sitemap index - extract referenced sitemap URLs
                    for sitemap in sitemap_tags:
                        loc = sitemap.find("loc")
                        if loc:
                            ref_sitemap_url = loc.get_text(strip=True)
                            if ref_sitemap_url not in processed_sitemaps:
                                sitemap_urls_to_process.append(ref_sitemap_url)
                else:
                    # Regular sitemap - extract URLs
                    for loc in soup.find_all("loc"):
                        u = loc.get_text(strip=True)
                        norm = normalize_url(u, rules=rules)
                        if norm not in seen:
                            if allowed and urlparse(norm).netloc not in allowed:
                                continue
                            if len(records) >= limits.max_pages:
                                break
                            seen.add(norm)
                            records.append(
                                URLRecord(
                                    url=norm,
                                    discovered_from=sitemap_url,
                                    depth=0,
                                    discovered_at=datetime.utcnow(),
                                    state=ProcessingState.DISCOVERED,
                                )
                            )
            except Exception:
                pass

    # Crawl internal links with depth limit
    depth = 0
    while queue and len(records) < limits.max_pages:
        batch = queue[: limits.max_pages - len(records)]
        queue = queue[len(batch) :]
        for url, from_url, d in batch:
            if d > limits.max_depth:
                continue
            if allowed and urlparse(url).netloc not in allowed:
                continue
            if url not in seen:
                seen.add(url)
                records.append(
                    URLRecord(
                        url=url,
                        discovered_from=from_url,
                        depth=d,
                        discovered_at=datetime.utcnow(),
                        state=ProcessingState.DISCOVERED,
                    )
                )
            try:
                with httpx.Client(timeout=15, follow_redirects=True, trust_env=False) as client:
                    r = client.get(url)
                    if r.status_code != 200:
                        continue
                    soup = BeautifulSoup(r.text, "lxml")
                    for a in soup.find_all("a", href=True):
                        href = a["href"].strip()
                        if not href or href.startswith("#") or href.startswith("mailto:"):
                            continue
                        full = urljoin(url, href)
                        norm = normalize_url(full, url, rules=rules)
                        if norm not in seen and (not allowed or urlparse(norm).netloc in allowed):
                            if d + 1 <= limits.max_depth:
                                queue.append((norm, url, d + 1))
            except Exception:
                pass

    # Deduplicate by url, keep sitemap-discovered first
    by_url: dict[str, URLRecord] = {}
    for rec in records:
        if rec.url not in by_url:
            by_url[rec.url] = rec
    return list(by_url.values())[: limits.max_pages]
