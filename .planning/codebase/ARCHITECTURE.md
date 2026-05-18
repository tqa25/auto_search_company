# Architecture

> Generated: 2026-05-18 | Source: auto_search_company

## System Overview

Auto Search Company is a **multi-step pipeline system** that automates Vietnamese company contact information extraction from the web. It follows a linear pipeline architecture with database-backed checkpointing and resume capability.

## Pipeline Flow (5 Steps)

1. **Step 1 — Gemini Quick Search** (`gemini_quick_search.py`): Fast lookup via Gemini + Google Search Grounding. If sufficient (phone + high confidence), skip to done.
2. **Step 2 — Google Maps** (`serper_search.py → search_places`): Structured phone/address from Serper Places API.
3. **Step 3 — Deep Search** (`serper_search.py → search + build_fallback_queries`): Organic Google Search with smart query construction. Results pass through `LinkFilter` for scoring.
4. **Step 4 — Scrape** (`scrape_module.py`): Top-N scored URLs scraped via Firecrawl API to Markdown.
5. **Step 5 — AI Extract** (`ai_extractor.py`): Gemini extracts structured contacts from scraped Markdown. Conflict resolution picks highest confidence.

### Fallback: Contact Discovery
If no phone found after Step 5, `ScrapeModule.discover_contact_pages()` tries `/contact`, `/lien-he`, `/about` paths on the company's official website.

## Company Status State Machine

`pending → searching → searched → filtering → filtered → scraping → scraped → extracting → ai_done → done`

Errors: `failed` (retryable) or `permanently_failed` (max retries).

## Key Design Patterns

### 1. Checkpoint-Resume Pipeline
`Pipeline` tracks company status in DB. On restart, resumes from last completed step. Signal handlers (`SIGINT`, `SIGTERM`) ensure graceful shutdown.

### 2. Tiered Search with Early-Stop
Step 1 is fast/cheap. If sufficient → skip Steps 2-4. In filtering, if enough high-scoring links found → early-stop.

### 3. Adaptive Rate Limiting
`AdaptiveRateLimiter`: 10 successes → -0.5s delay; 429 → 2x delay; 403/503 → max delay + 5min cooldown.

### 4. URL Deduplication (Multi-layer)
1. Query-level: SHA-256 hash prevents duplicate searches
2. URL-level: `url_cache` table with content hash and TTL
3. Cross-company: Same URL scraped once, reused
4. Grounding dedup: Serper results filtered against Gemini sources

### 5. Error Classification Hierarchy
- `RetryableError` → retry with backoff (429, timeout)
- `SkippableError` → skip company, continue batch
- `CriticalError` → stop pipeline (402, DB corrupt)

### 6. Conflict Resolution
Multiple sources → highest `confidence_score` wins. Conflicts logged.

## Module Dependency Graph

```
Pipeline (orchestrator)
├── GeminiQuickSearch → Database, Logger, Config
├── SerperSearch → Database, Logger, Config
├── LinkFilter → Database, Logger, Config
├── ScrapeModule → Database, Logger, Config, RateLimiter, ConnectionPool
├── AIExtractor → Database, Logger
├── ResultAggregator → Database
├── ExcelReader/Writer
├── HealthMonitor → Database, Logger
├── AdaptiveRateLimiter (standalone)
└── ConnectionManager (standalone)

Dashboard (FastAPI)
├── Database, Config, Logger
├── Pipeline (for step execution)
└── HealthMonitor
```

## Data Flow

```
Excel Input → companies table → Pipeline orchestration
  → search_results → filtered_links → scraped_pages → extracted_contacts
  → ResultAggregator → Excel Final Report
```

## Entry Points

| Entry Point | File | Purpose |
|-------------|------|---------|
| Pipeline CLI | `src/pipeline.py` | Direct pipeline execution |
| Dashboard | `dashboard/app.py` | Web UI + API for monitoring and execution |
| Batch scripts | `batch_gemini_quick.py`, `run_pipeline_test.py` | Targeted batch processing |
| Smoke test | `smoke_test.py` | End-to-end pipeline validation |
