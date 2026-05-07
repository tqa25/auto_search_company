# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Automated pipeline to find Vietnamese company contact information from an Excel input list. Given company names (in English, possibly with tax codes), it:
1. Searches Vietnamese business registries and directories via Firecrawl
2. Filters and classifies the result URLs by source type
3. Scrapes page content via Firecrawl
4. Extracts structured contact data (address, phone, email, etc.) using Google Gemini AI
5. Writes an Excel report

## Environment Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in project root:
```
FIRECRAWL_API_KEY=...
GEMINI_API_KEY=...
```

## Common Commands

```bash
# Run the main batch pipeline (always needs --limit)
python scripts/run_batch.py --limit 100

# Dry run to preview without executing
python scripts/run_batch.py --limit 100 --dry-run

# Resume from last checkpoint
python scripts/run_batch.py --resume --limit 100

# Retry failed companies
python scripts/run_batch.py --retry-failed

# Run quality evaluation on extracted contacts
python scripts/run_evaluation.py

# Run integration test (uses real Excel file from project root)
python tests/test_integration_phase1.py

# Run a specific unit test module
python -m pytest tests/test_database.py -v

# Run all tests
python -m pytest tests/ -v
```

## Architecture

### Data Flow

```
Excel input → companies table → search_results → filtered_links → scraped_pages → extracted_contacts → Excel report
```

### Database (`data/company_data.db`)

SQLite, managed by `src/database.py`. Six tables:
- `companies`: input list, with `status` field tracking pipeline progress
- `search_results`: raw Firecrawl search results
- `filtered_links`: classified URLs (by source_type) ready for scraping
- `scraped_pages`: markdown content from Firecrawl scrape
- `extracted_contacts`: structured fields from Gemini AI extraction
- `pipeline_logs`: step-level audit trail with timestamps and credits

### Company Status Machine (`src/pipeline.py`)

```
pending → searching → searched → scraping → scraped → extracting → done
                                                                  ↑
failed (retryable) ──────────────────────────────────────────────┘
permanently_failed (after max retries exceeded)
```

The pipeline is resumable: each step checkpoints the status to DB so an interrupted run can continue from where it left off.

### Search Strategy (`src/search_module.py`)

Three-tier bilingual search per company:
1. Tax code search (if available) — most precise
2. English name + Vietnamese anchor keywords (forces domestic business results)
3. Vietnamese translated name via Gemini (only if step 2 didn't hit `masothue.com` or `thuvienphapluat.vn`)

### Link Classification (`src/filter_module.py`)

URLs are classified into `source_type` values: `masothue`, `yellowpages`, `thuvienphapluat`, `hosocongty`, `vietnamworks`, `topcv`, `vietcareer`, `facebook`, `linkedin`, `official_website`, or `other`. Domains in `SKIP_DOMAINS` (news sites, social aggregators) are dropped.

### AI Extraction (`src/ai_extractor.py`)

Calls Gemini (`gemini-3-flash-preview`) with a Vietnamese-language prompt for each scraped page. Pages are processed in priority order (masothue first, social media last). Handles 429 rate limiting with 60s backoff, truncates markdown >30,000 chars.

### Key Source Modules

| File | Role |
|---|---|
| `src/pipeline.py` | Orchestrator: runs all 4 steps, handles resume/retry/shutdown |
| `src/database.py` | All DB reads/writes; each method opens and closes its own connection |
| `src/search_module.py` | Firecrawl search, Gemini translation |
| `src/filter_module.py` | URL classification |
| `src/scrape_module.py` | Firecrawl scrape |
| `src/ai_extractor.py` | Gemini contact extraction |
| `src/result_aggregator.py` | Aggregates `extracted_contacts` for reporting |
| `src/excel_handler.py` | Read input Excel; write final report (2 sheets: details + summary stats) |
| `src/health_monitor.py` | Console dashboard, credit usage tracking, time estimates |
| `src/logger.py` | Structured step logging to `pipeline_logs` table |
| `scripts/run_batch.py` | CLI entry point for production runs |

### Output Files

All generated files land in `output/` (Excel reports, CSV logs). The SQLite DB lives in `data/`. Scripts in `scripts/` are standalone runners for specific scenarios (pilot batches, evaluation, etc.).

## Key Constraints

- **Firecrawl credits**: 2 credits per search, 1 per scrape page. The `HealthMonitor` tracks usage. HTTP 402 from Firecrawl means credits exhausted — the pipeline stops immediately.
- **Gemini rate limit**: Free tier is 15 RPM. `AIExtractor` sleeps 60s on 429 and retries up to 3 times.
- **`DatabaseManager` is not thread-safe**: each call opens a new SQLite connection. Don't share instances across threads.
- **Input Excel format**: `ExcelReader` auto-detects columns by scanning headers for keywords like "company name (english)" and "tax code" (case-insensitive). It skips rows without a string company name.
