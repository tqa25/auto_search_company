# Implementation status

Last updated: 2026-08-18 +07
Overall state: Stage 1 Work Item 3 (retry) — code complete and independently
verified against the acceptance criteria in
`docs/v2-stage1-critical-fixes-implementation-plan.md` §6.8. Docs in sync.

Read first: `docs/architecture/MAP.md` (how the system works) and `docs/architecture/INDEX.md` (which contract doc covers what).

## Stage 0 — complete

30-company baseline accepted (commits `2bdbba7`, `8cd7558`). Files:
`docs/implementation/work-items/stage0-baseline.md`, `stage0-url-checklist.md`,
`stage0_raw_query_results.json`. Verified against the live DB (8/30 random, 80 field
checks, zero mismatches); `data/company_data.db` untouched.

## Current handoff

| Work item | State | Gate |
|---|---|---|
| WI1 — remove fixed waits (§4) | **held** | §4.1b A/B measurement spends real Firecrawl credit |
| WI2 — cache-hit + unique index (§5) | **held** | migration writes to `data/company_data.db` (1.98 GB); needs backup |
| WI3 — retry correctness (§6) | **code complete, verified** | none — zero paid API, zero schema change |

WI3 on branch `refactor/stage1-retry-executor`:

A first pass claimed "code complete" but an independent re-check against
`docs/v2-stage1-critical-fixes-implementation-plan.md` §6.8 found 6 real gaps.
All were fixed in a second pass:

- `src/v2/runtime/retry.py`: `base_delay` corrected 1.0s → 2.0s (policy default);
  HTTP 408 added to retryable codes; `classify_error()` gained
  `retry_after_seconds` — a 429 now carries the provider's `Retry-After` value
  on `RetryableError.retry_after`, and `_calculate_delay()` honors it instead of
  computing exponential backoff; new module function `parse_retry_after()`
  parses both delta-seconds and HTTP-date header forms; `execute()` gained
  `should_stop=` (interruptible backoff via `_interruptible_sleep`, polling
  every 0.5s instead of a blocking `time.sleep`) and `context=` (structured
  per-attempt logging: company_id, operation, provider, attempt, max_attempts,
  status, decision, delay_seconds, duration_ms — no secrets logged).
- `src/search_module.py`, `src/scrape_module.py`, `src/firecrawl_deep_search.py`:
  parse the `Retry-After` response header on 429 and pass it into
  `classify_error(...)`.
- `src/gemini_quick_search.py`: the catch-all exception handler no longer
  swallows unclassified errors into a fake-successful empty result — it now
  classifies via `classify_error()` and re-raises, so transient failures reach
  the retry/status-mapping layer instead of being reported as "searched, found
  nothing."
- `tests/test_retry.py`: 12 new tests added (timeout/5xx retry-then-succeed
  sequences, Retry-After header honored as delay, `parse_retry_after` both
  forms, should_stop interrupts backoff early, structured log fields present,
  retry doesn't duplicate a side effect, connection_pool status-retry disabled,
  rate_limiter has no call-triggering method) — 35/35 passing, run 3x with no
  flakiness. One pre-existing test (`test_exponential_backoff_with_jitter`)
  had hardcoded interval bounds assuming the old 1.0s base_delay; updated to
  match the corrected 2.0s default.

**Known residual scope gap — not fixed, flagged for a follow-up, not silently
dropped:** `should_stop` is implemented and unit-tested in `RetryExecutor.execute()`,
but no production call site passes it yet. `search_module.py`, `scrape_module.py`,
`firecrawl_deep_search.py`, `ai_extractor.py` all call `execute()` without a
`should_stop` argument. In production, a shutdown request today still waits out
an in-progress backoff sleep — the interrupt *mechanism* exists and is correct,
it is just not wired to `JobController.should_stop()` yet. Wiring it requires
threading an optional `should_stop` parameter through `company_run.py` →
`search_module.search()` / `scrape_module` / `ai_extractor` call chains, which
was judged out of scope for this fix pass (it touches call signatures beyond
the two files the original bug report named) and is left as explicit follow-up
work, not silently assumed done.

Next action: none blocking — WI3 is done. WI1 and WI2 remain **held** pending a
user decision on spending real API credit / touching the live DB.

Standing facts — do not re-derive, do not redo:

- The Korean Blacklist/Skip **executive** and **domain-evidence** reports are both
  COMPLETE for the verified window 22/05–14/07/2026. Detail in `work-items/`.
- Artifact `output/reports/blacklist-skip-domain-evidence-ko.html` is local only
  (`output/` is gitignored).
- If the domain-evidence report is regenerated, preserve the explicit `dauthau.info`
  Gemini Grounding provenance rule **first**.
- The replay estimate is a conservative Top-10 simulation, not an invoice total.

## Verification

`venv/bin/python -m pytest tests/ -q` → **225 passed, 1 failed**
(`test_dashboard_import_filters.py::test_runner_restart_worker_starts_new_process_after_terminating_runtime_workers`,
`KeyError: 'stopped_pids'`, pre-existing baseline failure, unrelated to WI3).
`tests/test_retry.py` re-run 3x standalone with no flakiness (35/35 each run).
Doc gate: `bash scripts/check-doc-sync.sh` — passes after `./scripts/gen-symbols.sh`.
