"""Configuration loader for page classification system."""

import json
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


class CrawlLimits(BaseModel):
    """Crawl limits configuration."""

    max_depth: int = Field(default=3, ge=0)
    max_pages: int = Field(default=1000, ge=1)
    rate_per_second: float = Field(default=2.0, ge=0.1)


class RenderPolicy(BaseModel):
    """When to invoke render_tool."""

    min_text_chars: int = Field(default=300)
    spa_markers: list[str] = Field(
        default_factory=lambda: ["__NEXT_DATA__", "data-reactroot", "__NUXT__", "ng-version"]
    )
    force_render: bool = Field(default=False)


class RetryPolicy(BaseModel):
    """Retry configuration for transient failures."""

    max_attempts: int = Field(default=3, ge=1)
    backoff_seconds: float = Field(default=2.0, ge=0)


class LLMProviderConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = Field(default="openai")
    model: str = Field(default="gpt-4o-mini")
    api_key_env: str = Field(default="OPENAI_API_KEY")
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_tokens: int = Field(default=1024, ge=1)


class OutputConfig(BaseModel):
    """Output configuration."""

    storage_path: str = Field(default="./output/results.db")
    export_format: Optional[str] = Field(default="jsonl")
    text_excerpt_max_length: int = Field(default=5000, ge=100)


class Config(BaseModel):
    """Full system configuration."""

    start_urls: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    crawl_limits: CrawlLimits = Field(default_factory=CrawlLimits)
    url_normalization_rules: dict[str, Any] = Field(default_factory=dict)
    render_policy: RenderPolicy = Field(default_factory=RenderPolicy)
    ruleset_path: str = Field(default="config/ruleset.json")
    term_dictionaries_path: str = Field(default="config/term_dictionaries")
    llm_provider_config: LLMProviderConfig = Field(default_factory=LLMProviderConfig)
    output_config: OutputConfig = Field(default_factory=OutputConfig)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        """Load config from YAML file."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """Load config from dictionary."""
        return cls(**data)


def load_config(path: str | Path) -> Config:
    """Load configuration from file (YAML or JSON)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        content = f.read()

    if path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(content) or {}
    else:
        data = json.loads(content)

    return Config.from_dict(data)
