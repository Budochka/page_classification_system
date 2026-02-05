"""Term scores structure for page classification."""

from pydantic import BaseModel, Field


class TermScores(BaseModel):
    """Keyword match counts per audience category (Russian dictionaries)."""

    investor_beginner: int = Field(0, ge=0)
    investor_qualified: int = Field(0, ge=0)
    issuer_beginner: int = Field(0, ge=0)
    issuer_advanced: int = Field(0, ge=0)
    professional: int = Field(0, ge=0)

    def to_dict_for_llm(self) -> dict:
        """Format for LLM input."""
        return {
            "investor_beginner": self.investor_beginner,
            "investor_qualified": self.investor_qualified,
            "issuer_beginner": self.issuer_beginner,
            "issuer_advanced": self.issuer_advanced,
            "professional": self.professional,
        }
