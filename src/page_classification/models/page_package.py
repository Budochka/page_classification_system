"""Page classification package - compact representation for rules and LLM."""

from typing import Optional

from pydantic import BaseModel, Field

from .term_scores import TermScores


class PageMeta(BaseModel):
    """Meta information extracted from page."""

    title: Optional[str] = None
    description: Optional[str] = None
    h1: Optional[str] = None
    canonical: Optional[str] = None
    robots: Optional[str] = None


class PageContent(BaseModel):
    """Content extracted from page."""

    text_excerpt: str = Field(default="", max_length=10000)
    headings: list[str] = Field(default_factory=list)
    key_paragraphs: list[str] = Field(default_factory=list, max_length=7)


class PageStructure(BaseModel):
    """Structural signals from page."""

    breadcrumbs: list[str] = Field(default_factory=list)
    nav_section_hints: list[str] = Field(default_factory=list)
    cta_texts: list[str] = Field(default_factory=list)
    forms_detected: bool = False
    schema_types: list[str] = Field(default_factory=list)


class PageSignals(BaseModel):
    """Computed signals for classification."""

    term_scores: TermScores = Field(default_factory=TermScores)
    readability_proxy: Optional[float] = None
    tables_count: int = 0
    lists_count: int = 0
    numbers_ratio: Optional[float] = None
    acronym_ratio: Optional[float] = None
    is_article_like: bool = False
    is_doc_like: bool = False
    has_api_keywords: bool = False


class PagePackage(BaseModel):
    """
    Mandatory schema for page classification.
    Converts noisy HTML into compact, stable, explainable representation.
    """

    # Page
    url: str = ""
    final_url: str = ""
    status: Optional[int] = None
    fetch_mode: str = Field(default="http", pattern="^(http|render)$")
    content_type: Optional[str] = None
    content_hash: Optional[str] = None

    # Meta, Content, Structure, Signals
    meta: PageMeta = Field(default_factory=PageMeta)
    content: PageContent = Field(default_factory=PageContent)
    structure: PageStructure = Field(default_factory=PageStructure)
    signals: PageSignals = Field(default_factory=PageSignals)

    def to_llm_input(self) -> dict:
        """Serialize for LLM consumption."""
        return {
            "url": self.url,
            "final_url": self.final_url,
            "status": self.status,
            "fetch_mode": self.fetch_mode,
            "content_type": self.content_type,
            "meta": self.meta.model_dump(),
            "content": {
                "text_excerpt": self.content.text_excerpt[:2000],  # Limit for context
                "headings": self.content.headings,
                "key_paragraphs": self.content.key_paragraphs,
            },
            "structure": self.structure.model_dump(),
            "signals": {
                "term_scores": self.signals.term_scores.to_dict_for_llm(),
                "readability_proxy": self.signals.readability_proxy,
                "tables_count": self.signals.tables_count,
                "lists_count": self.signals.lists_count,
                "is_article_like": self.signals.is_article_like,
                "is_doc_like": self.signals.is_doc_like,
                "has_api_keywords": self.signals.has_api_keywords,
            },
        }
