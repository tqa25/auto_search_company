# Implementation status

Last updated: 2026-08-18 +07
Overall state: Stage 1 Work Item 3 (retry) — code complete, independently
verified against `docs/v2-stage1-critical-fixes-implementation-plan.md` §6.8,
then put through an independent 8-angle code review that found and fixed
4 more real bugs. Docs in sync.

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
| WI3 — retry correctness (§6) | **code complete, verified twice** | none — zero paid API, zero schema change |

WI3 on branch `refactor/stage1-retry-executor` went through two verification
passes, each finding real bugs the previous pass had missed:

**Pass 1** (self re-check against §6.8 acceptance criteria) fixed: `base_delay`
1.0s → 2.0s, HTTP 408 added to retryable codes, `Retry-After` header honored
via `classify_error(..., retry_after_seconds=)` and `parse_retry_after()`,
`execute()` gained `should_stop=` (interruptible backoff) and `context=`
(structured per-attempt logging), `gemini_quick_search.py` stopped swallowing
unclassified errors into a fake-successful empty result, 12 new tests added.

**Pass 2** (independent 8-angle code review, one verifier agent per candidate
finding, none of it self-graded) found and fixed 4 more real bugs, all now
fixed and re-verified — 225 passed / 1 pre-existing baseline failure, no new
regressions:

- `src/firecrawl_deep_search.py`: a `Retry-After` parse was gated on
  `resp.status_code == 429` while already nested inside an
  `if resp.status_code == 200:` block — dead code, introduced during Pass 1,
  that could never fire. Removed the dead guard; `classify_error()` now
  attaches `retry_after_seconds` to every `RetryableError` it returns
  (previously only for the literal 429 case), not just the ones it happened
  to special-case.
- `src/v2/runtime/retry.py`: `_interruptible_sleep()` re-checked `should_stop()`
  one extra time after the backoff delay had already fully elapsed, so it
  could report "interrupted" even when the sleep completed normally. Now
  returns `False` unconditionally once the loop exits by elapsed time.
- `src/ai_extractor.py`: the retry-executor migration had silently dropped a
  resilience path — the old code fell back from the primary Gemini model to
  `models/gemini-3.5-flash` after repeated 503s; `gemini_quick_search.py` kept
  this fallback, `ai_extractor.py` lost it. No data loss (checkpoint stayed at
  `ai_extract_pending`), but extraction failed outright during a Gemini outage
  instead of trying the cheaper model first. Restored: `_do_extract()` now
  takes the model name as a parameter, and after the primary model's full
  attempt budget is exhausted with a `RetryableError`, one more full attempt
  cycle runs against the fallback model before giving up.
- `src/reparse_module.py`: `reextract()` already isolated per-page failures
  correctly (one bad page never aborted the rest of the loop — that part was
  never broken), but on exception it logged and moved on without recording
  anything in `results` for that page, so a failed page silently vanished from
  the UI instead of showing as failed. Now appends
  `{"status": "failed", "reason": ..., "page_id": ...}`.

**Known residual scope gap — not fixed, flagged for a follow-up, not silently
dropped:** `should_stop` is implemented and unit-tested in `RetryExecutor.execute()`,
but no production call site passes it yet. `search_module.py`, `scrape_module.py`,
`firecrawl_deep_search.py`, `ai_extractor.py` all call `execute()` without a
`should_stop` argument — a shutdown request today still waits out an
in-progress backoff sleep. Wiring it requires threading an optional
`should_stop` parameter through `company_run.py` → each adapter's call chain,
judged out of scope for a targeted bug-fix pass. Independently confirmed by
the Pass 2 review (not just self-reported).

Also noted by Pass 2, not fixed (cleanup/consistency, not correctness):
`gemini_quick_search.py` still hand-rolls string matching for its 429/503
special cases instead of using `classify_error()` for everything; the
`Retry-After`-header-extraction pattern is duplicated near-identically across
5 call sites instead of one shared helper; code and doc updates for this work
item were committed separately rather than atomically per AGENTS.md §7 (the
final tree still passes `check-doc-sync.sh`, but individual commits in the
history don't each carry their own doc update).

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
