"""Extract tool - build page_package from HTML."""

import hashlib
import re
from pathlib import Path

from bs4 import BeautifulSoup

from ..config.loader import Config
from ..models.page_package import (
    PagePackage,
    PageMeta,
    PageContent,
    PageStructure,
    PageSignals,
)
from ..models.term_scores import TermScores


SPA_MARKERS = ["__NEXT_DATA__", "data-reactroot", "__NUXT__", "ng-version"]


def _load_term_dictionaries(path: str | Path) -> dict[str, list[str]]:
    """Load Russian keyword dictionaries."""
    path = Path(path)
    categories = [
        "investor_beginner",
        "investor_qualified",
        "issuer_beginner",
        "issuer_advanced",
        "professional",
    ]
    result: dict[str, list[str]] = {}
    for cat in categories:
        f = path / f"{cat}.txt"
        if f.exists():
            result[cat] = [
                line.strip().lower()
                for line in f.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            result[cat] = []
    return result


def _count_terms(text: str, keywords: list[str]) -> int:
    """Count keyword occurrences in text (case-insensitive)."""
    t = text.lower()
    return sum(1 for kw in keywords if kw in t)


def _extract_text(soup: BeautifulSoup, max_length: int = 5000) -> str:
    """Extract main text from body, stripped."""
    body = soup.find("body")
    if not body:
        return ""
    for tag in body.find_all(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = body.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text[:max_length]


def _key_paragraphs(soup: BeautifulSoup, max_count: int = 7) -> list[str]:
    """Extract most informative paragraphs (article/main content)."""
    paras: list[str] = []
    for tag in soup.find_all(["p", "article", "section"]):
        t = tag.get_text(separator=" ", strip=True)
        if len(t) > 80:
            paras.append(t[:500])
    return paras[:max_count]


def _has_spa_markers(html: str, markers: list[str]) -> bool:
    return any(m in html for m in markers)


def _compute_readability_proxy(text: str) -> float | None:
    """Simple readability proxy: avg word length, sentence length."""
    if not text:
        return None
    words = text.split()
    if not words:
        return None
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    avg_word = sum(len(w) for w in words) / len(words)
    avg_sent = len(words) / len(sentences) if sentences else 0
    return (avg_word + avg_sent) / 2


def extract_tool(
    url: str,
    html: str,
    final_url: str,
    http_status: int,
    fetch_mode: str,
    content_type: str,
    config: Config,
) -> PagePackage:
    """
    Build page_package from HTML.
    Extracts meta, content, structure, signals, term_scores.
    """
    # Use XML parser for XML content, HTML parser for HTML
    if content_type and "xml" in content_type.lower():
        soup = BeautifulSoup(html, "xml")
    else:
        soup = BeautifulSoup(html, "lxml")
    output_config = config.output_config
    max_excerpt = output_config.text_excerpt_max_length

    text = _extract_text(soup, max_excerpt)
    headings = [h.get_text(strip=True) for h in soup.find_all(["h2", "h3"])]
    key_paras = _key_paragraphs(soup)

    # Meta
    meta = PageMeta(
        title=soup.title.string.strip() if soup.title and soup.title.string else None,
        description=None,
        h1=None,
        canonical=None,
        robots=None,
    )
    desc = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    if desc and desc.get("content"):
        meta.description = desc["content"].strip()
    h1_tag = soup.find("h1")
    if h1_tag:
        meta.h1 = h1_tag.get_text(strip=True)
    canon = soup.find("link", rel="canonical")
    if canon and canon.get("href"):
        meta.canonical = canon["href"]
    robots = soup.find("meta", attrs={"name": "robots"})
    if robots and robots.get("content"):
        meta.robots = robots["content"]

    # Structure
    breadcrumbs: list[str] = []
    for bc in soup.find_all(class_=re.compile(r"breadcrumb|nav-breadcrumb", re.I)):
        breadcrumbs.extend(bc.stripped_strings)
    nav_hints: list[str] = []
    for nav in soup.find_all(["nav", "aside"]):
        for a in nav.find_all("a"):
            t = a.get_text(strip=True)
            if t and len(t) < 100:
                nav_hints.append(t)
    cta_texts: list[str] = []
    for btn in soup.find_all(["button", "a"], class_=re.compile(r"btn|cta|primary", re.I)):
        t = btn.get_text(strip=True)
        if t:
            cta_texts.append(t)
    forms = bool(soup.find("form"))
    schema_types: list[str] = []
    for s in soup.find_all("script", type="application/ld+json"):
        if s.string and "organization" in s.string.lower():
            schema_types.append("Organization")
        if s.string and "article" in s.string.lower():
            schema_types.append("Article")

    # Search scope for terms
    search_text = " ".join(
        [
            text[:3000],
            " ".join(headings),
            " ".join(cta_texts),
            " ".join(nav_hints),
            " ".join(breadcrumbs),
        ]
    )

    # Term scores
    dicts_path = config.term_dictionaries_path
    dicts = _load_term_dictionaries(dicts_path)
    term_scores = TermScores(
        investor_beginner=_count_terms(search_text, dicts.get("investor_beginner", [])),
        investor_qualified=_count_terms(search_text, dicts.get("investor_qualified", [])),
        issuer_beginner=_count_terms(search_text, dicts.get("issuer_beginner", [])),
        issuer_advanced=_count_terms(search_text, dicts.get("issuer_advanced", [])),
        professional=_count_terms(search_text, dicts.get("professional", [])),
    )

    # Signals
    tables = len(soup.find_all("table"))
    lists = len(soup.find_all(["ul", "ol"]))
    digits = sum(1 for c in text if c.isdigit())
    numbers_ratio = digits / len(text) if text else None
    acronyms = len(re.findall(r"\b[A-ZА-Я]{2,}\b", text))
    acronym_ratio = acronyms / max(len(text.split()), 1)
    is_article = "article" in [t.name for t in soup.find_all()] or "Article" in schema_types
    is_doc = ".pdf" in url or "document" in content_type.lower() or "doc" in url.lower()
    api_kw = ["api", "fix", "торговый шлюз", "подключение к торгам"]
    has_api = any(kw in text.lower() for kw in api_kw)

    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()[:32]

    return PagePackage(
        url=url,
        final_url=final_url,
        status=http_status,
        fetch_mode=fetch_mode,
        content_type=content_type,
        content_hash=content_hash,
        meta=meta,
        content=PageContent(
            text_excerpt=text,
            headings=headings,
            key_paragraphs=key_paras,
        ),
        structure=PageStructure(
            breadcrumbs=breadcrumbs[:20],
            nav_section_hints=nav_hints[:30],
            cta_texts=cta_texts[:20],
            forms_detected=forms,
            schema_types=list(set(schema_types)),
        ),
        signals=PageSignals(
            term_scores=term_scores,
            readability_proxy=_compute_readability_proxy(text),
            tables_count=tables,
            lists_count=lists,
            numbers_ratio=numbers_ratio,
            acronym_ratio=acronym_ratio,
            is_article_like=is_article,
            is_doc_like=is_doc,
            has_api_keywords=has_api,
        ),
    )
