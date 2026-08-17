# Codebase Map

**Read this file first, every session. It replaces reading the codebase.**

Derived from source on 2026-08-14 by reading `pipeline.py`, `company_run.py`,
`completion_audit.py`, `pipeline_worker.py`, `database.py`, `dashboard/app.py`.
Every claim below was verified against code, not inherited from older docs.

Scope: 33 Python files, ~13,000 lines. Python + SQLite + FastAPI + vanilla-JS SPA.

---

## 1. What this system does

Takes a list of company names (Excel import), and for each company finds
contact data (phone, address, email, website, tax code) by searching the web,
scraping candidate pages, and extracting fields with an LLM. Results land in
SQLite and are exported to Excel. Vietnamese company data domain.

External services actually called:

- **Gemini** — `gemini_quick_search.py`, `ai_extractor.py`
- **Firecrawl** — `firecrawl_deep_search.py`, `scrape_module.py`, `search_module.py`

**Serper was removed** (2026-08-14). It had never been wired up: no module
called it, `src/serper_search.py` never existed, and the dashboard's
`serper_search` step raised `ModuleNotFoundError` on invocation. The config
keys, the settings-page fields, the `serper_api_key` plumbing and the always-zero
"Serper credits" line in the batch summary are all gone.

One artifact remains on purpose: the `daily_quota.serper_used` column, kept so
existing databases are not rewritten. Nothing reads or increments it.

---

## 2. The pipeline — 5 steps, one company at a time

Defined in `src/company_run.py::CompanyRun._run_attempt` (the real orchestrator).
`src/pipeline.py::Pipeline` owns config, modules, signals and batch stats; it
delegates each company to `CompanyRun`.

| # | Step | Module | Writes to |
|---|---|---|---|
| 1 | Gemini Quick Search | `src/gemini_quick_search.py` | `gemini_quick_results` |
| 2 | Deep Search (Firecrawl/Serper) | `src/firecrawl_deep_search.py` | `search_results` |
| 3 | Filter + score URLs | `src/filter_module.py` | `filtered_links` |
| 4 | Scrape pages | `src/scrape_module.py` | `scraped_pages` |
| 5 | AI extract fields | `src/ai_extractor.py` | `extracted_contacts` |

Two behaviours that are easy to miss:

- **Step 3 usually runs *inside* step 2**, not after it. Deep search calls
  `filter_urls_incremental` per query batch and sets `filter_already_completed`,
  so the standalone filter step is skipped
  (`company_run.py:188` and `company_run.py:219`).
- **Early stop**: deep search breaks out of the query loop once
  `EARLY_STOP_COUNT` links score >= `EARLY_STOP_SCORE` (`company_run.py:198`).

### Business status gate (before scraping)

`Pipeline._run_business_status_gate` (`pipeline.py:187`) scrapes up to 3
registry domains (masothue.com, thuvienphapluat.vn, …) to read the company's
legal status. If the category is `INACTIVE_STOP` (dissolved/suspended), the
company is finalized as **`done` immediately** — deliberately bypassing strict
completion, because an inactive company will never have full contacts and
marking it `failed` would re-queue it forever (`company_run.py:232-242`).

---

## 3. State machine — `companies.status`

This column is the single source of truth for resume. Transition table lives at
`src/pipeline.py:27` (`Pipeline.STATUS_FLOW`), mapping *current status* →
*step to resume from*.

```
pending ──► gemini_quick ──► gemini_quick_done ──► searching ──► searched
                                                                    │
                                                                    ▼
                                                                 scraping
                                                                    │
                                                    ★ ai_extract_pending
                                                                    │
                                                               extracting
                                                                    │
                                                                 ai_done
                                                                    │
                                                                   done
```

- `-ing` statuses (`gemini_quick`, `searching`, `scraping`, `extracting`) mean
  **interrupted mid-step**; each maps back to the start of that step.
- ★ `ai_extract_pending` is the **key checkpoint**: scraping is done and saved,
  AI has not run. Resuming from here skips re-scraping — the expensive part.
  A `CriticalError` during extraction preserves this status on purpose
  (`company_run.py:101-103`).
- Terminal: `done`, `permanently_failed`. Both are skipped by `CompanyRun.run`.
- `failed` → resumes from `gemini_quick` (full restart).
  `retry_failed(max_retries=2)` promotes it to `permanently_failed` past the limit.

### Strict completion — why a company is *not* `done`

`src/completion_audit.py::audit_company_completion` is the gatekeeper. Reaching
step 5 does **not** mark a company `done`. It requires:

1. Top-N scrape candidates exist (`TOP_N` env, default 10), and
2. none are `missing` (never attempted), and
3. none are `blocking` (failed with a retryable error), and
4. `extracted_contacts` count > 0.

`completion_audit.py:7` treats `success`, `timeout`, `skipped`, `unsupported` as
**terminal (non-blocking)**. But only **four** values are ever written to
`scraped_pages.scrape_status`: `success`, `failed`, `timeout`, `skipped` (all via
`database.py::insert_scraped_page`, called only from `scrape_module.py`).
`unsupported` is never persisted — it is only *derived* from `error_message` text
by `_classify_scrape_result`. So in practice the only blocking status is
`failed`, and only when its error text matches no "unsupported" marker.

If the audit fails, it returns a `resume_status` and the company is rewound to
that status instead of being marked done (`company_run.py::_finalize_strict_done`).
This is the usual cause of "the company keeps re-running."

**Candidates and scrape results join on `url`, not `filtered_link_id`** —
`filtered_links` is re-inserted on every run, so one URL has many rows while
`scraped_pages` has one. Joining by id marked every duplicate "missing" and made
strict completion unreachable. Documented in `completion_audit.py:26-30`.

---

## 4. Entry points

| Command | File | Purpose |
|---|---|---|
| `python scripts/run_batch.py --limit N` | `scripts/run_batch.py` | Batch CLI. Also `--resume`, `--retry-failed`, `--dry-run`, `--offset`, `--delay`. Prompts for confirmation. |
| `python -m src.pipeline_worker` | `src/pipeline_worker.py` | Long-running queue worker. Claims jobs from `pipeline_jobs`. |
| `python dashboard/run.py` | `dashboard/run.py` | FastAPI dashboard + SPA. |
| `scripts/export_csv.py`, `export_final.py` | — | Excel/CSV exports. |
| `scripts/backfill_stuck_searched.py` | — | One-off repair for stuck rows. |

`scripts/pipeline_worker.py` (11 lines) is a thin shim to `src/pipeline_worker.py`.

### Two execution modes coexist

- **Direct**: `run_batch.py` → `Pipeline.run()` → loops companies in-process.
  Graceful shutdown via SIGINT/SIGTERM; finishes the current company then stops.
- **Queued**: dashboard enqueues into `pipeline_jobs`; `PipelineWorker.run_once`
  claims a job (`claim_next_pipeline_job`), runs the same `Pipeline`, and reports
  progress via `WorkerJobController` (heartbeat + `requested_action='stop'`).

`PipelineWorker.recover_stale_jobs` re-queues jobs whose heartbeat is older than
`stale_minutes` (default 15), using `suggest_resume_status` to infer where to
restart from actual row counts rather than trusting `status`.

The recovery policy lives in **`src/resume_policy.py`** — `company_data_counts`
and `suggest_resume_status`. Both the worker and `dashboard/app.py` import it.
It is deliberately dependency-free so the dashboard does not pull `Pipeline` into
its import graph. It used to be copy-pasted into both files; do not re-inline it.

---

## 5. Data model — SQLite (`data/company_data.db`)

Schema is created in `src/database.py::init_db`. **18 tables.**

**Core chain** (each row links to the previous stage):
```
companies ─< search_results ─< filtered_links ─< scraped_pages ─< extracted_contacts
          └─< gemini_quick_results
```

| Table | Role |
|---|---|
| `companies` | Master record + `status` state machine + `business_status` |
| `gemini_quick_results` | Step 1 output, incl. token counts, `is_sufficient` |
| `search_results` | Raw search hits (query, rank, url, snippet) |
| `filtered_links` | Scored/filtered URLs, `should_scrape`, `relevance_score` |
| `scraped_pages` | Markdown content, `scrape_status`, `error_message` |
| `extracted_contacts` | Final fields: address, phone, email, website, fax, representative |
| `pipeline_logs` | Per-step audit trail; drives `_latest_activity` |
| `pipeline_jobs` | Queue: status, checkpoint, progress, heartbeat, `requested_action` |
| `pipeline_workers` | Worker liveness registry |
| `query_cache` / `url_cache` | TTL caches (`expires_at` / `ttl_expires_at`) |
| `daily_quota` | Per-day counters. `gemini_grounding_used` is live; `serper_used` is dead (§1) |
| `domain_stats` | Per-domain scrape counts + `is_auto_blacklisted` |
| `company_import_batches` / `company_import_items` / `company_match_candidates` | Excel import + fuzzy name matching |
| `report_runs` / `reported_companies` | Report snapshots |
| `schema_version` | Migration bookkeeping |

### ⚠️ Schema evolution is NOT in `migrations.py`

`src/migrations.py` has an **empty** `MIGRATIONS = []` registry — it is currently
inert. Real column additions are inline `ALTER TABLE` calls inside
`database.py::init_db` (see lines 97-127, 166, 369-375), wrapped to tolerate
"duplicate column" errors. **To add a column, edit `database.py::init_db`**, not
`migrations.py`. Any doc saying otherwise is stale.

---

## 6. Dashboard

`dashboard/app.py` (2,782 lines — the largest file) is FastAPI serving both the
SPA shell and the JSON API. Frontend is vanilla JS in
`dashboard/frontend/assets/app.js` (no build step).

- **SPA routes** (return HTML shell): `/`, `/companies`, `/companies/{id}`,
  `/runner`, `/settings`, `/logs`
- **Data API**: `/api/spa/*` — companies (list/ids/detail), monitor, logs,
  settings, pipeline-config, import-batches, runtime-health
- **Control API**: `/api/spa/runner/{start,stop-all,reset-status,restart-worker}`,
  `/api/runner/step`, `/api/companies/import`, `/api/export-excel`
- **WebSockets**: `/ws/monitor` (job progress), `/ws/logs` (live log stream)
- Auth via `auth_middleware` (`app.py:55`); responses cached with
  `_cache_get`/`_cache_set` (TTL `_DASHBOARD_CACHE_SECONDS`), invalidated by
  `_invalidate_dashboard_cache`.

The dashboard can spawn/reap worker processes directly
(`_start_worker_process`, `_reap_extra_workers`, `_ensure_worker_started`).

---

## 7. Error taxonomy — `src/errors.py`

Behaviour is defined by which exception a module raises. This is the main
control-flow lever in `CompanyRun._run_with_retries`.

| Exception | Handling |
|---|---|
| `RetryableError` | Retry up to 2x with 60s × attempt backoff, then `failed` |
| `SkippableError` | Mark `failed` — **unless** the audit says `strict_done`, then `done` |
| `CriticalError` | Preserve `ai_extract_pending` checkpoint, then **abort the whole batch** |
| any other `Exception` | Mark `failed`, continue to next company |

Hierarchy is flat: all three subclass `PipelineError(Exception)` directly. Each
carries `(message, company_id, step)` and a `category` property.

---

## 8. Supporting modules

| File | Role |
|---|---|
| `src/config.py` | `Config` class (annotated attrs, not a dataclass) + `default_config`; env vars, then `pipeline_config.json` overrides |
| `src/database.py` | `DatabaseManager`: schema, queries, job queue ops |
| `src/resume_policy.py` | Where to restart an interrupted company. Reads row counts instead of trusting `companies.status`. Shared by the worker and the dashboard. |
| `src/connection_pool.py` | **HTTP** client pooling — `ConnectionManager` wraps `requests.Session` with `HTTPAdapter`/`Retry`, max 5 conns, per-type timeouts (search 15s, scrape 45s). Nothing to do with SQLite. |
| `src/rate_limiter.py` | `AdaptiveRateLimiter` — **throttling only**. 429 doubles delay, 403/503 → max delay + 5-min cooldown. Daily-quota enforcement is *not* here; it lives in `gemini_quick_search.py:94`. |
| `src/logger.py` | `PipelineLogger` → `pipeline_logs` + JSONL event stream + daily summaries + CSV/Excel export |
| `src/excel_handler.py` | `ExcelReader` / `ExcelWriter`. `write_consolidated_report` (`:377`) emits **3** sheets: Summary, Detail, Foreign Exclusions — its own docstring says 2 and is wrong. |
| `src/company_matcher.py` | Exact normalized-tax-code match first, then `difflib` fuzzy name scoring. Called from `dashboard/app.py:2326` on import. |
| `src/result_aggregator.py` | **Collects** contacts one-per-row into a `sources` list per company + attaches per-step status. Does *not* merge or dedupe. |
| `src/business_status.py` | Parses legal status from registry pages; `ACTIVE`, `INACTIVE_STOP`, `INACTIVE_ADDRESS`, `UNKNOWN` |
| `src/reparse_module.py` | ⚠️ **Costs Firecrawl credits.** Unlocks links previously filtered out, scrapes URLs that were *never* scraped (`scrape_unlocked` → `ScrapeModule.scrape_url`), then re-extracts. It is not a cache-only replay. |
| `src/schemas.py` | 4 dataclasses (`SearchResult`, `ScoredLink`, `ScrapedContent`, `ExtractedContact`) + `validate_*` boundary helpers raising `ValueError` |
| `src/utils.py` | One function: `normalize_url` (lowercase host, strip `www.`/trailing slash/`utm_*`/`fbclid`) |
| `src/time_utils.py` | Vietnam-timezone helpers — **always use these, not `datetime.now()`** |
| `src/search_module.py` | Legacy path. Only reached via the `else` branch at `company_run.py:207` when Gemini returned nothing, or manual `run_step('search')`. |

`replay_mode=True` (a `Pipeline.run` argument) is the zero-API-call path: it
skips search, scrape and extract and re-runs logic over existing DB rows. Use it
to test pipeline changes. **Do not confuse it with `reparse_module`, which does
spend credits.**

### Key config defaults (`src/config.py`)

`SEARCH_LIMIT=100`, `EARLY_STOP_COUNT=10`, `EARLY_STOP_SCORE=35`,
`GEMINI_DAILY_LIMIT=1450`, `FORCE_REFRESH=False`,
`BUSINESS_STATUS_GATE_ENABLED=True`.
The first three and the last are overridable from `pipeline_config.json`;
`GEMINI_DAILY_LIMIT` and `FORCE_REFRESH` are **env-only** (`config.py:257-267`).

---

## 9. Known traps

1. `'search'` is a **sentinel, not a step**. `_get_next_step` returns it for any
   unknown status; it is absent from `_should_do_step`'s `step_order`, so
   everything runs. That is intentional ("start from scratch") and
   `company_run.py:39` uses `next_step != "search"` to decide whether to print
   "Resuming". Don't "fix" it by adding `'search'` to `step_order`.
2. `migrations.py` is inert (§5).
3. Strict completion, not step completion, decides `done` (§3).
4. `filtered_links` accumulates duplicate URLs across runs — always dedupe by
   `url` when joining.
5. `Pipeline.generate_report` has a legacy fallback branch that triggers only if
   `ExcelWriter.write_final_report` is missing. Dead in practice.
6. **`force_refresh` is a partial bypass.** It flips the global
   `cfg.FORCE_REFRESH` (`company_run.py:42`, reset in a `finally`), which only
   skips the `query_cache` / `url_cache` *table* lookups
   (`search_module.py:470`, `scrape_module.py:82,398`). The separate
   "already have a successful `scraped_pages` row" checks
   (`scrape_module.py:107-115,426-434`) are **not** gated by it — a
   force-refresh run still reuses existing scraped content.
7. **Auto-blacklist is read once at startup.** `LinkFilter.__init__`
   (`filter_module.py:102-106`) loads `get_auto_blacklisted_domains()` into
   memory and uses it at `filter_module.py:321`. A long-running worker never
   sees domains blacklisted after it started — restart it to pick them up.
   The flag is written from `ai_extractor.py:186` (extraction outcome), not from
   the scrape module; `scrape_module.py` never reads it.
8. Method params are named `delay_seconds`, not `delay`
    (`ScrapeModule.scrape_company`, `AIExtractor.extract_for_company`).

---

## 10. Tests

```
venv/bin/python -m pytest tests/ -q
```

Baseline as of 2026-08-14: **190 passed, 1 failed**. The known failure is
`test_dashboard_import_filters.py::test_runner_restart_worker_starts_new_process_after_terminating_runtime_workers`
(`KeyError: 'stopped_pids'` — the endpoint no longer returns that key). Treat it
as pre-existing; anything beyond it is yours.

Tests are named per module (`test_filter_module.py`, `test_scrape_module.py`,
`test_database.py`, …). See `docs/architecture/INDEX.md` for the
change → test mapping. JS tests: `tests/*.test.mjs` (`node --test`).

---

## 11. Keeping this file true

This map is only worth its tokens if it stays accurate.

- Structural change (new step, new status, new table, new entry point) →
  update the affected section here **in the same commit**.
- Public function/class added or moved → run `./scripts/gen-symbols.sh`.
- Nothing else needs updating. Do not append changelogs or status reports here;
  this file describes the system as it is now, not its history.
