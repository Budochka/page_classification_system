"""Classification result from LLM."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


ALLOWED_LABELS = frozenset({
    "INVESTOR_BEGINNER",
    "INVESTOR_QUALIFIED",
    "ISSUER_BEGINNER",
    "ISSUER_ADVANCED",
    "PROFESSIONAL",
    "OTHER",
})

# Priority order (higher = override lower)
LABEL_PRIORITY = {
    "PROFESSIONAL": 6,
    "ISSUER_ADVANCED": 5,
    "ISSUER_BEGINNER": 4,
    "INVESTOR_QUALIFIED": 3,
    "INVESTOR_BEGINNER": 2,
    "OTHER": 1,
}


class ClassificationResult(BaseModel):
    """Strict JSON output from classify_llm_tool."""

    labels: list[str] = Field(..., description="List of labels. If OTHER, must be exactly ['OTHER']. Otherwise can be multiple labels.")
    confidence: float = Field(..., ge=0.0, le=1.0)
    matched_rules: list[str] = Field(default_factory=list)
    rationale: str = Field(default="")
    evidence: list[str] = Field(default_factory=list)
    needs_review: bool = Field(default=False)
    missing_signals: list[str] = Field(default_factory=list)
    
    @property
    def label(self) -> str:
        """Backward compatibility: return first label or 'OTHER'."""
        if not self.labels:
            return "OTHER"
        return self.labels[0]


class StoredClassification(BaseModel):
    """Validated result for storage - includes all required fields."""

    url: str
    final_url: str
    http_status: Optional[int]
    labels: list[str] = Field(..., description="List of labels. If OTHER, must be exactly ['OTHER'].")
    confidence: float
    matched_rules: list[str]
    rationale: str
    evidence: list[str]
    needs_review: bool
    ruleset_version: str
    model_version: str
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    fetch_mode: str = "http"
    content_hash: Optional[str] = None
    
    @property
    def label(self) -> str:
        """Backward compatibility: return first label or 'OTHER'."""
        if not self.labels:
            return "OTHER"
        return self.labels[0]
