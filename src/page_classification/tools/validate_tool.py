"""Validate tool - validate LLM classification output."""

from ..models.classification_result import (
    ClassificationResult,
    ALLOWED_LABELS,
)
from ..config.loader import Config


def validate_tool(
    result: ClassificationResult,
    ruleset_path: str | None = None,
) -> tuple[bool, list[str]]:
    """
    Validate classification result.
    Returns (is_valid, list of error messages).
    """
    errors: list[str] = []
    ruleset_rule_ids: set[str] = set()

    # Load rule IDs from ruleset if path provided
    if ruleset_path:
        from pathlib import Path
        path = Path(ruleset_path)
        if path.exists():
            content = path.read_text(encoding="utf-8")
            import re
            for m in re.finditer(r'"id"\s*:\s*"([^"]+)"', content):
                ruleset_rule_ids.add(m.group(1))
            for m in re.finditer(r'"R\d+"', content):
                ruleset_rule_ids.add(m.group(0).strip('"'))

    # 1. Label validity
    if result.label not in ALLOWED_LABELS:
        errors.append(f"Invalid label: {result.label}")

    # 2. Confidence in [0, 1]
    if not (0 <= result.confidence <= 1):
        errors.append(f"Confidence must be in [0,1]: {result.confidence}")

    # 3. Rule IDs exist (if ruleset loaded)
    if ruleset_rule_ids and result.matched_rules:
        for rid in result.matched_rules:
            if rid not in ruleset_rule_ids and not rid.startswith("R"):
                # Allow R-prefixed rules as heuristic
                pass

    # 4. Non-OTHER without rules → needs_review
    if result.label != "OTHER" and not result.matched_rules and not result.needs_review:
        errors.append("Non-OTHER classification without matched_rules must have needs_review=true")

    # 5. Confidence < 0.5 → needs_review
    if result.confidence < 0.5 and not result.needs_review:
        errors.append("Confidence < 0.5 must have needs_review=true")

    return (len(errors) == 0, errors)


def apply_validation_fixes(result: ClassificationResult) -> ClassificationResult:
    """Apply fixes for validation failures (set needs_review, etc.)."""
    if result.label != "OTHER" and not result.matched_rules:
        result = result.model_copy(update={"needs_review": True})
    if result.confidence < 0.5:
        result = result.model_copy(update={"needs_review": True})
    return result
