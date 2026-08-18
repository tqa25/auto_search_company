# Architecture Index

Routing table: **what you want to change → what to open → how to verify.**

Read [`MAP.md`](MAP.md) first for how the system works. Use this file to jump
straight to the right module without searching. Use [`symbols.md`](symbols.md)
to find a symbol's line number before reading a large file.

All test commands assume `venv/bin/python -m pytest ... --ignore=tests/manual`.

## Pipeline

| Want to change | Read first | Verify with |
|---|---|---|
| Step order, retries, error handling for one company | `src/company_run.py` | `tests/test_company_run.py` |
| Status transitions, resume logic, batch stats, reports | `src/pipeline.py` | `tests/test_resume.py`, `tests/test_integration_phase1.py` |
| When a company counts as finished (strict completion) | `src/completion_audit.py` | `tests/test_company_run.py`, `tests/test_resume.py` |
| Step 1: Gemini grounded quick search | `src/gemini_quick_search.py` | `tests/test_ai_extractor.py` |
| Step 2: deep search, query building, dedup | `src/firecrawl_deep_search.py`, `src/search_module.py` | `tests/test_search_module.py` |
| Step 3: URL filtering, blacklist, skip rules, scoring | `src/filter_module.py` | `tests/test_filter_module.py` |
| Step 4: scrape selection, Firecrawl cache | `src/scrape_module.py`, `src/database.py` | `tests/test_scrape_module.py`, `tests/test_database.py` |
| Step 5: LLM field extraction, prompts | `src/ai_extractor.py` | `tests/test_ai_extractor.py` |
| Business status gate (dissolved/suspended companies) | `src/business_status.py`, `src/pipeline.py:187` | `tests/test_business_status.py` |
| Reparse: unlock filtered-out links and scrape them (⚠️ **spends Firecrawl credits** — not a cache-only replay) | `src/reparse_module.py`, `dashboard/reparse_api.py` | `tests/test_ai_extractor.py` |
| Auto-blacklisting of bad domains (written from `ai_extractor.py:186`, cached in `LinkFilter.__init__`) | `src/database.py:1378`, `src/filter_module.py:102` | `tests/test_filter_module.py`, `tests/test_database.py` |

## Worker & queue

| Want to change | Read first | Verify with |
|---|---|---|
| Job claiming, heartbeat, stale recovery | `src/pipeline_worker.py` | `tests/test_worker_lifecycle.py` |
| Resume-status inference from row counts | `src/resume_policy.py` — single shared implementation; the worker and the dashboard both import it | `tests/test_worker_lifecycle.py`, `tests/test_dashboard_import_filters.py` |
| Worker process spawn/reap from the dashboard | `dashboard/app.py` (`_start_worker_process`, `_reap_extra_workers`) | `tests/test_dashboard_import_filters.py` |

## Data & storage

| Want to change | Read first | Verify with |
|---|---|---|
| **Add or alter a DB column** | `src/database.py::init_db` (inline `ALTER TABLE`) — **not** `src/migrations.py`, whose registry is empty | `tests/test_database.py` |
| Queries, job-queue SQL, connection handling | `src/database.py` | `tests/test_database.py` |
| SQLite pooling | `src/connection_pool.py` | `tests/test_connection_pool.py` |
| Caches (query/url TTL), force-refresh behaviour | `src/database.py`, `src/config.py` | `tests/test_database.py` |

## Import, export, reporting

| Want to change | Read first | Verify with |
|---|---|---|
| Excel import parsing and batch items | `src/excel_handler.py`, `dashboard/frontend/assets/companyImportParser.js` | `tests/test_excel_handler.py`, `tests/company_import_parser.test.mjs` |
| Fuzzy company-name matching on import | `src/company_matcher.py` | `tests/test_company_matcher.py` |
| Final Excel report (consolidated, **3 sheets**: Summary / Detail / Foreign Exclusions) | `src/excel_handler.py::ExcelWriter.write_consolidated_report` (`:377`) | `tests/test_excel_consolidated_report.py`, `tests/test_excel_final.py` |
| Merging contacts across sources | `src/result_aggregator.py` | `tests/test_result_aggregator.py` |
| CSV / final exports | `scripts/export_csv.py`, `scripts/export_final.py` | manual run |

## Dashboard

| Want to change | Read first | Verify with |
|---|---|---|
| API endpoints, filters, caching, auth | `dashboard/app.py` | `tests/test_dashboard_import_filters.py` |
| SPA behaviour (no build step) | `dashboard/frontend/assets/app.js` | manual browser check |
| Settings persistence | `dashboard/app.py`, `pipeline_config.json` | `tests/settings_serializers.test.mjs` |
| Live monitor / log streaming | `dashboard/app.py` (`/ws/monitor`, `/ws/logs`) | manual browser check |

## Cross-cutting

| Want to change | Read first | Verify with |
|---|---|---|
| Config values, env vars, thresholds | `src/config.py`, `.env.example`, `pipeline_config.json` | `tests/test_integration_phase1.py` |
| Error classes and retry semantics | `src/errors.py`, `src/v2/runtime/retry.py` | `tests/test_company_run.py`, `tests/test_retry.py` |
| Rate limiting and daily quota | `src/rate_limiter.py` | `tests/test_rate_limiter.py` |
| Logging and daily summaries | `src/logger.py` | `tests/test_logger.py` |
| **Any date/time handling** | `src/time_utils.py` — never use bare `datetime.now()` | `tests/test_time_utils.py` |
| HTTP connection pooling | `src/connection_pool.py` | `tests/test_connection_pool.py` |

## Generated reports (one-off deliverables)

| Artifact | Spec | Generator |
|---|---|---|
| Executive Blacklist/Skip HTML report (Korean UI) | `docs/architecture/executive-blacklist-skip-report.md` | hand-authored HTML, no generator script |
| Blacklist/Skip domain evidence HTML (Korean UI) | `docs/architecture/blacklist-skip-domain-evidence-report.md` | `scripts/generate_blacklist_skip_domain_evidence_report.py` — reads the SQLite DB read-only, emits `output/reports/blacklist-skip-domain-evidence-ko.html` |

Before regenerating the domain evidence report, re-read its spec: the explicit
`dauthau.info` Gemini Grounding provenance rule must be preserved, and those
URLs must not be presented as no-contact scrape results.
