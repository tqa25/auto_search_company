# Project Structure

> Generated: 2026-05-18 | Source: auto_search_company

## Directory Layout

```
auto_search_company/
├── .env.example              # Environment template (FIRECRAWL, GEMINI, SERPER keys)
├── .gitignore                # Ignores .env, *.db, output/, venv/, __pycache__, *.xlsx
├── CLAUDE.md                 # AI assistant context file
├── requirements.txt          # Python dependencies (7 packages)
│
├── src/                      # ═══ CORE PIPELINE MODULES ═══
│   ├── __init__.py
│   ├── config.py             # Central Config class — all thresholds, limits, toggles
│   ├── pipeline.py           # Pipeline orchestrator — 5-step flow with checkpointing (744 lines)
│   ├── database.py           # DatabaseManager — SQLite WAL, thread-local, schema creation (396 lines)
│   ├── schemas.py            # Pydantic-style dataclasses & validators (129 lines)
│   ├── errors.py             # PipelineError hierarchy (Retryable/Skippable/Critical) (52 lines)
│   │
│   ├── gemini_quick_search.py  # Step 1: Gemini + Google Search Grounding (388 lines)
│   ├── serper_search.py        # Steps 2-3: Serper Maps + Deep Search (346 lines)
│   ├── search_module.py        # Legacy: Firecrawl-based search (717 lines)
│   ├── filter_module.py        # URL scoring & classification engine (508 lines)
│   ├── scrape_module.py        # Step 4: Firecrawl web scraping (416 lines)
│   ├── ai_extractor.py         # Step 5: Gemini AI contact extraction (731 lines)
│   │
│   ├── logger.py             # PipelineLogger — DB + JSONL + colored console (322 lines)
│   ├── rate_limiter.py       # AdaptiveRateLimiter — dynamic delay adjustment (211 lines)
│   ├── connection_pool.py    # ConnectionManager — HTTP session pooling + retry (207 lines)
│   ├── health_monitor.py     # HealthMonitor — credit tracking, ETA, dashboard (289 lines)
│   ├── evaluator.py          # QualityEvaluator — extraction quality grading (214 lines)
│   ├── result_aggregator.py  # ResultAggregator — cross-company data aggregation (123 lines)
│   └── excel_handler.py      # ExcelReader/Writer — input/output Excel files (365 lines)
│
├── dashboard/                # ═══ WEB DASHBOARD (FastAPI) ═══
│   ├── __init__.py
│   ├── app.py                # FastAPI app — routes, WebSocket, API endpoints (719 lines)
│   ├── run.py                # Uvicorn launcher script
│   ├── static/               # CSS, JavaScript assets
│   └── templates/            # Jinja2 HTML templates
│       ├── base.html         # Base layout with navigation
│       ├── monitor.html      # Progress dashboard (/)
│       ├── companies.html    # Company list (/companies)
│       ├── company_detail.html  # Single company view (/companies/{id})
│       ├── runner.html       # Pipeline execution UI (/runner)
│       ├── settings.html     # Config editor (/settings)
│       └── logs.html         # Log viewer (/logs)
│
├── tests/                    # ═══ TEST SUITE ═══
│   ├── __init__.py
│   ├── test_ai_extractor.py
│   ├── test_connection_pool.py
│   ├── test_database.py
│   ├── test_excel_handler.py
│   ├── test_excel_final.py
│   ├── test_filter_module.py
│   ├── test_health_monitor.py
│   ├── test_integration_phase1.py   # Multi-module integration test (17K lines)
│   ├── test_logger.py
│   ├── test_rate_limiter.py
│   ├── test_result_aggregator.py
│   ├── test_resume.py               # Pipeline checkpoint/resume tests (16K lines)
│   ├── test_scrape_module.py
│   └── test_search_module.py
│
├── data/                     # Database directory (*.db gitignored)
├── output/                   # Pipeline output (gitignored)
│   └── logs/                 # Daily JSONL log files
├── results/                  # Report output directory
│
├── scripts/                  # ═══ UTILITY SCRIPTS ═══
├── scratch/                  # Temporary scratch files
│
├── # ═══ ROOT-LEVEL SCRIPTS (legacy/ad-hoc) ═══
├── batch_gemini_quick.py     # Batch Gemini Quick Search runner
├── run_pipeline_test.py      # Pipeline test runner with specific companies
├── smoke_test.py             # End-to-end smoke test (22K lines)
├── evaluate_old_data.py      # Old data evaluation utility
├── export_detailed.py        # Detailed export script
├── verify_batching.py        # Batching verification
├── verify_today.py           # Today's results verification
├── test_firecrawl.py         # Firecrawl API test
├── test_gemini.py            # Gemini API test
├── test_gemini_grounding.py  # Gemini grounding test
├── test_scrape.py            # Scrape test
├── test_match.py             # Name matching test
├── test_new_scoring.py       # New scoring algorithm test
├── test_fuzz.py              # Fuzzy matching test
├── parse_full.py / 2 / 3    # Log parsing utilities
├── parse_logs.py             # Log parser
├── parse_timeline.py         # Timeline parser
├── patch_search_module.py    # Search module patch script
│
├── # ═══ DOCUMENTATION (root-level) ═══
├── FINAL_REPORT_VN_KR.md
├── HUONG_DAN_SMOKE_TEST.md
├── PIPELINE_ANALYSIS_REPORT.md
├── REPORT_2026-05-12.md
├── SMOKE_TEST_SUMMARY.md
├── pipeline_workflow_details.md
├── prompt_upgrade_plan.md
├── implementation_plan_A/B/C/d.md
├── workflow_3d.html          # 3D pipeline visualization
├── workflow_diagram.html     # Interactive workflow diagram
│
├── Plan/                     # Legacy plan documents
├── agent_prompt/             # AI agent prompt templates
└── .planning/                # GSD planning directory
    └── codebase/             # This codebase map
```

## Module Size Distribution

| Module | Lines | Complexity |
|--------|-------|------------|
| `pipeline.py` | 744 | High — orchestration, signals, checkpointing |
| `ai_extractor.py` | 731 | High — batching, early-stop, conflict resolution |
| `dashboard/app.py` | 719 | Medium — routes, WebSocket, API |
| `search_module.py` | 717 | Medium — 2-tier search, caching (legacy) |
| `filter_module.py` | 508 | Medium — scoring engine, fuzzy matching |
| `scrape_module.py` | 416 | Medium — dedup, retries, contact discovery |
| `database.py` | 396 | Medium — schema, CRUD, thread-local |
| `gemini_quick_search.py` | 388 | Medium — quota, grounding, fallback |
| `excel_handler.py` | 365 | Low — I/O formatting |
| `serper_search.py` | 346 | Low — API client, query builder |
| `logger.py` | 322 | Low — logging infrastructure |
| `health_monitor.py` | 289 | Low — stats aggregation |
| `evaluator.py` | 214 | Low — quality grading |
| `rate_limiter.py` | 211 | Low — delay management |
| `connection_pool.py` | 207 | Low — session wrapper |
| `schemas.py` | 129 | Low — data validation |
| `result_aggregator.py` | 123 | Low — data merging |
| `errors.py` | 52 | Trivial — exception classes |

**Total core source**: ~6,100 lines across 18 modules.
