"""Data models for page classification system."""

from .url_record import URLRecord, ProcessingState, TERMINAL_STATES
from .page_package import PagePackage
from .term_scores import TermScores
from .classification_result import (
    ClassificationResult,
    StoredClassification,
    ALLOWED_LABELS,
    LABEL_PRIORITY,
)

__all__ = [
    "URLRecord",
    "ProcessingState",
    "TERMINAL_STATES",
    "PagePackage",
    "TermScores",
    "ClassificationResult",
    "StoredClassification",
    "ALLOWED_LABELS",
    "LABEL_PRIORITY",
]
