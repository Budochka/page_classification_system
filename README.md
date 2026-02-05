# Page Classification System for Exchange Websites

Automatically crawls an exchange website, processes each page, and classifies it into **one or more target audience categories** using rule-based logic supported by an LLM. Optimized for large Russian-language websites.

## Classification Labels

Each page can be classified with **one or more labels** from the following categories:

| Label | Description |
|-------|-------------|
| `INVESTOR_BEGINNER` | Retail / non-qualified investors, educational, onboarding |
| `INVESTOR_QUALIFIED` | Qualified or experienced investors, complex instruments |
| `ISSUER_BEGINNER` | Issuers that have never done a placement (IPO, first bond) |
| `ISSUER_ADVANCED` | Issuers with completed placements (disclosure, corporate actions) |
| `PROFESSIONAL` | Brokers, management companies, funds, clearing/depository |
| `OTHER` | Generic news, errors, mixed or unclear pages |

### Multiple Labels

- Pages can have **multiple labels** if they serve multiple audiences (e.g., `["INVESTOR_BEGINNER", "ISSUER_BEGINNER"]`)
- The `OTHER` label **cannot be combined** with other labels - if a page is `OTHER`, it will only have `["OTHER"]`
- The LLM analyzes page content to determine which audiences the page serves

## Architecture

```
[MCP Agent]
   ├── crawl_tool      → Collect URLs from sitemap and links
   ├── fetch_tool      → Retrieve HTML via HTTP
   ├── render_tool     → Render SPA pages (Playwright)
   ├── extract_tool    → Build page_package (meta, content, term_scores)
   ├── classify_llm_tool → LLM classification with rules
   ├── validate_tool   → Validate LLM output
   └── storage_tool    → Persist results
```

## Setup

### 1. Install dependencies

```bash
cd page_classification_system
pip install -r requirements.txt
```

### 2. Install Playwright (optional, for SPA rendering)

```bash
playwright install chromium
```

### 3. Configure

Edit `config/config.yaml`:

- `start_urls`: URLs to crawl
- `allowed_domains`: Domain whitelist
- `crawl_limits`: max_depth, max_pages, rate
- `llm_provider_config`: 
  - `model`: OpenAI model name (e.g., `gpt-5-nano`, `gpt-4o-mini`)
  - `api_key_env`: Environment variable name for API key (default: `OPENAI_API_KEY`)
  - Set the API key: `export OPENAI_API_KEY=your-key-here` (Linux/Mac) or `$env:OPENAI_API_KEY="your-key-here"` (PowerShell)

### 4. Set API Key

```bash
# Linux/Mac
export OPENAI_API_KEY=your-api-key-here

# Windows PowerShell
$env:OPENAI_API_KEY = "your-api-key-here"
```

### 5. Run

```bash
# From project root
python -m page_classification.main -c config/config.yaml -v
```

Or using the convenience script:

```bash
py run.py -c config/config.yaml -v
```

## Configuration

| Key | Description |
|-----|-------------|
| `start_urls` | Seed URLs for crawling |
| `allowed_domains` | Domain whitelist (default: derived from start_urls) |
| `crawl_limits.max_depth` | Max link depth |
| `crawl_limits.max_pages` | Max pages to process |
| `render_policy.force_render` | Always use Playwright for SPA |
| `ruleset_path` | Path to ruleset JSON |
| `term_dictionaries_path` | Directory with Russian keyword files |
| `llm_provider_config.model` | OpenAI model name (e.g., `gpt-5-nano`, `gpt-4o-mini`) |
| `llm_provider_config.api_key_env` | Environment variable name for API key |
| `llm_provider_config.temperature` | Only for non-GPT-5 models (GPT-5 uses default 1) |
| `llm_provider_config.max_tokens` | Token limit (converted to `max_completion_tokens` for GPT-5) |
| `output_config.storage_path` | Output file (`.jsonl` or `.db`) |

## Updating Rules and Keywords

### Rules

Edit `config/ruleset.json`. Rules help guide classification, but the LLM analyzes content to determine which labels apply. A page can match multiple rules and receive multiple labels. Priority order (for reference):
1. PROFESSIONAL
2. ISSUER_ADVANCED
3. ISSUER_BEGINNER
4. INVESTOR_QUALIFIED
5. INVESTOR_BEGINNER
6. OTHER

**Important:** The `OTHER` label cannot be combined with other labels. If a page is classified as `OTHER`, it will only have `["OTHER"]` as its label.

### Russian Keyword Dictionaries

Edit files in `config/term_dictionaries/`:

- `investor_beginner.txt`
- `investor_qualified.txt`
- `issuer_beginner.txt`
- `issuer_advanced.txt`
- `professional.txt`

One keyword per line. Used for `term_scores` in the page package.

## Output Format

Results are stored as JSONL (one JSON object per line) or SQLite. Each record includes:

- `url`, `final_url`, `http_status`
- `labels` (array of strings), `confidence`
- `matched_rules`, `rationale`, `evidence`
- `needs_review`
- `ruleset_version`, `model_version`, `processed_at`
- `fetch_mode`, `content_hash`

**Example output:**
```json
{
  "url": "https://example.com/page",
  "labels": ["INVESTOR_BEGINNER", "ISSUER_BEGINNER"],
  "confidence": 0.85,
  "matched_rules": ["R5", "R8"],
  "rationale": "Page serves both beginner investors and first-time issuers",
  ...
}
```

**Note:** For backward compatibility, the `label` property (singular) is available and returns the first label in the `labels` array.

## LLM Model Support

### GPT-5 Models (gpt-5-nano, gpt-5-mini, gpt-5, etc.)

- Use `max_completion_tokens` instead of `max_tokens` (automatically handled)
- Do not support `temperature` parameter (uses default value of 1)
- Recommended for cost-effective classification tasks

### Other Models (gpt-4o-mini, gpt-4o, etc.)

- Use `max_tokens` parameter
- Support `temperature` parameter for controlling randomness

## Determinism and Replayability

- Each classification stores `page_package`, `ruleset_version`, `model_version`
- Reprocessing the same inputs yields comparable results
- For non-GPT-5 models, use `temperature: 0` for LLM determinism
- GPT-5 models use fixed temperature (1) and may have slight variation

## License

MIT
