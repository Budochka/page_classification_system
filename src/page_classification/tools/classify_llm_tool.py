"""Classify LLM tool - invoke LLM for page classification."""

import json
import logging
import os
import time
from pathlib import Path

import httpx
from openai import OpenAI

from ..config.loader import Config
from ..models.page_package import PagePackage
from ..models.classification_result import ClassificationResult, ALLOWED_LABELS

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a page classifier for an exchange website.
Classify each page into one or more labels based on target audience:
- INVESTOR_BEGINNER: Retail/non-qualified investors, educational, onboarding
- INVESTOR_QUALIFIED: Qualified/experienced investors, complex instruments, higher risks
- ISSUER_BEGINNER: Issuers that have never done a placement (IPO, first bond, initial listing)
- ISSUER_ADVANCED: Issuers that have completed placements (disclosure, corporate actions, secondary)
- PROFESSIONAL: Professional participants (brokers, management companies, funds, clearing/depository)
- OTHER: Pages that do not clearly belong to any audience above

IMPORTANT RULES:
1. If a page clearly belongs to multiple audiences, return multiple labels (e.g., ["INVESTOR_BEGINNER", "ISSUER_BEGINNER"])
2. If a page is OTHER, return ONLY ["OTHER"] (never combine OTHER with other labels)
3. Analyze the actual page content (text_excerpt, headings, key_paragraphs, meta) to understand the page's purpose and target audience
4. Do not rely solely on pre-computed signals (term_scores, has_api_keywords). Read and understand the content to make an informed classification.

CRITICAL: You must return ONLY valid JSON. Do not include markdown code blocks, do not include any explanatory text before or after the JSON. Return ONLY the JSON object.

If uncertain or the page doesn't fit any specific audience, return ["OTHER"]."""

USER_PROMPT_TEMPLATE = """Ruleset (use as guidelines, but analyze content first):
{ruleset}

Allowed labels: {allowed_labels}

Page package:
{page_package}

Analyze the page content carefully:
1. Read the text_excerpt, headings, and key_paragraphs to understand what the page is about
2. Check the meta information (title, description, h1) for context
3. Consider the structure (breadcrumbs, nav hints, CTAs) to understand the page's purpose
4. Use term_scores and other signals as supporting evidence, not the primary factor
5. Match rules that align with your content analysis

Return ONLY valid JSON (no markdown, no code blocks, no extra text):
{{
  "labels": ["LABEL1", "LABEL2"],  // Array of labels. Can be multiple, but if OTHER, must be ONLY ["OTHER"]
  "confidence": 0.0-1.0,
  "matched_rules": ["R1", "R2"],
  "rationale": "Brief explanation based on content analysis",
  "evidence": ["field=value", ...],
  "needs_review": false,
  "missing_signals": []
}}

Remember: Return ONLY the JSON object, nothing else."""


def _load_ruleset(path: str | Path) -> str:
    """Load ruleset as human-readable string for LLM."""
    path = Path(path)
    if not path.exists():
        return "No ruleset loaded."
    content = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        try:
            data = json.loads(content)
            return json.dumps(data, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
    return content


def classify_llm_tool(
    page_package: PagePackage,
    config: Config,
    ruleset_path: str | None = None,
) -> ClassificationResult:
    """
    Invoke LLM with ruleset and page_package.
    Returns strict JSON: labels (list), confidence, matched_rules, rationale, evidence, needs_review, missing_signals.
    """
    ruleset_path = ruleset_path or config.ruleset_path
    ruleset = _load_ruleset(ruleset_path)
    allowed = ", ".join(sorted(ALLOWED_LABELS))
    pkg_json = json.dumps(page_package.to_llm_input(), ensure_ascii=False, indent=2)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        ruleset=ruleset,
        allowed_labels=allowed,
        page_package=pkg_json,
    )

    llm_config = config.llm_provider_config
    api_key = os.environ.get(llm_config.api_key_env, "")

    if not api_key:
        # Fallback: return OTHER with needs_review when no API key
        return ClassificationResult(
            labels=["OTHER"],
            confidence=0.0,
            matched_rules=[],
            rationale="No LLM API key configured. Manual review required.",
            evidence=[],
            needs_review=True,
            missing_signals=["llm_unavailable"],
        )

    # Disable proxy usage for OpenAI client (trust_env=False)
    client = OpenAI(
        api_key=api_key,
        http_client=httpx.Client(trust_env=False, timeout=60.0)
    )

    try:
        # GPT-5 models use max_completion_tokens instead of max_tokens
        # GPT-5 models don't support temperature parameter (only default 1)
        create_params = {
            "model": llm_config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        # GPT-5 models use max_completion_tokens, not max_tokens; no temperature support
        is_gpt5 = llm_config.model.startswith("gpt-5")
        if is_gpt5:
            create_params["max_completion_tokens"] = llm_config.max_tokens
        else:
            create_params["max_tokens"] = llm_config.max_tokens
            create_params["temperature"] = llm_config.temperature
        
        # Time the LLM call
        start_time = time.time()
        logger.debug("Calling LLM API for %s...", page_package.url)
        response = client.chat.completions.create(**create_params)
        elapsed = time.time() - start_time
        
        # Log token usage and timing
        usage = response.usage
        logger.info("LLM call completed in %.2fs for %s - prompt: %d tokens, completion: %d tokens (reasoning: %d)", 
                   elapsed, page_package.url, 
                   usage.prompt_tokens, usage.completion_tokens,
                   getattr(usage.completion_tokens_details, 'reasoning_tokens', 0) if hasattr(usage, 'completion_tokens_details') else 0)
        
        content = response.choices[0].message.content
        
        # Check if content is None or empty
        if not content:
            logger.error(f"Empty LLM response. Finish reason: {response.choices[0].finish_reason}")
            logger.error(f"Response object: {response}")
            return ClassificationResult(
                labels=["OTHER"],
                confidence=0.0,
                matched_rules=[],
                rationale="Empty response from LLM",
                evidence=[],
                needs_review=True,
                missing_signals=["empty_response"],
            )
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        
        # Try to get more details from OpenAI API errors
        if hasattr(e, 'response'):
            try:
                if hasattr(e.response, 'json'):
                    error_detail = e.response.json()
                    error_msg = f"{error_msg} - {error_detail}"
            except:
                pass
        
        logger.error(f"LLM API error: {error_type}: {error_msg}", exc_info=True)
        
        return ClassificationResult(
            labels=["OTHER"],
            confidence=0.0,
            matched_rules=[],
            rationale=f"LLM error ({error_type}): {error_msg}",
            evidence=[],
            needs_review=True,
            missing_signals=["llm_error"],
        )

    # Parse JSON - strip markdown code blocks and extract JSON from text
    raw = content.strip()
    
    # Remove markdown code blocks
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0].strip()
    
    # Try to extract JSON object from text (handle cases where LLM adds extra text)
    # Find the first { and matching } by counting braces
    start_idx = raw.find("{")
    if start_idx >= 0:
        brace_count = 0
        for i in range(start_idx, len(raw)):
            if raw[i] == "{":
                brace_count += 1
            elif raw[i] == "}":
                brace_count -= 1
                if brace_count == 0:
                    raw = raw[start_idx:i+1]
                    break
    
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        logger.error(f"LLM response (first 1000 chars): {content[:1000]}")
        logger.error(f"Cleaned response (first 500 chars): {raw[:500]}")
        return ClassificationResult(
            labels=["OTHER"],
            confidence=0.0,
            matched_rules=[],
            rationale=f"Invalid JSON from LLM: {str(e)[:100]}",
            evidence=[],
            needs_review=True,
            missing_signals=["parse_error"],
        )

    # Validate and coerce labels
    labels_raw = data.get("labels", data.get("label", "OTHER"))  # Support both "label" and "labels" for backward compatibility
    if isinstance(labels_raw, str):
        labels_raw = [labels_raw]  # Convert single label to list
    labels = [str(l).upper().strip() for l in labels_raw if l]
    
    # Validate labels
    valid_labels = []
    has_other = False
    for lbl in labels:
        lbl_upper = lbl.upper()
        if lbl_upper in ALLOWED_LABELS:
            if lbl_upper == "OTHER":
                has_other = True
            valid_labels.append(lbl_upper)
    
    # Enforce rule: OTHER cannot be combined with other labels
    if has_other:
        if len(valid_labels) > 1:
            logger.warning(f"OTHER cannot be combined with other labels. Using only OTHER. Original: {labels}")
        valid_labels = ["OTHER"]
    
    # If no valid labels, default to OTHER
    if not valid_labels:
        valid_labels = ["OTHER"]
    
    confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
    matched_rules = list(data.get("matched_rules", []) or [])
    rationale = str(data.get("rationale", ""))
    evidence = list(data.get("evidence", []) or [])
    needs_review = bool(data.get("needs_review", False))
    missing_signals = list(data.get("missing_signals", []) or [])

    return ClassificationResult(
        labels=valid_labels,
        confidence=confidence,
        matched_rules=matched_rules,
        rationale=rationale,
        evidence=evidence,
        needs_review=needs_review,
        missing_signals=missing_signals,
    )
