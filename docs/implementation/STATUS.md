# Implementation status

Last updated: 2026-08-18 +07
Overall state: Stage 1 Work Item 3 (retry) — **code complete**, docs pending update.

Read first: `docs/architecture/MAP.md` (how the system works) and `docs/architecture/INDEX.md` (which contract doc covers what).

## Stage 0 — complete

30-company baseline accepted (commits `2bdbba7`, `8cd7558`). Files:
`docs/implementation/work-items/stage0-baseline.md`, `stage0-url-checklist.md`,
`stage0_raw_query_results.json`. Verified against the live DB (8/30 random, 80 field
checks, zero mismatches); `data/company_data.db` untouched.

Known sample limitation: group A has no genuinely different-province pair — the four
sampled are same-address re-imports. One real pair exists if the sample ever needs
strengthening: MINH TRÍ, id=758 (Bắc Ninh) vs id=7290 (Hà Nội).

## Current handoff

| Work item | State | Gate |
|---|---|---|
| WI1 — remove fixed waits (§4) | **held** | §4.1b A/B measurement spends real Firecrawl credit |
| WI2 — cache-hit + unique index (§5) | **held** | migration writes to `data/company_data.db` (1.98 GB); needs backup |
| WI3 — retry correctness (§6) | **code complete** | none — zero paid API, zero schema change |

WI3 changes on branch `refactor/stage1-retry-executor`:
- Created `src/v2/runtime/retry.py` (RetryExecutor + classify_error)
- Added `MAX_ATTEMPTS` config (semantic: 1 initial + N retries)
- Deprecated `MAX_RETRIES` with warning
- Disabled HTTP-status retries in `connection_pool.py`
- Updated `firecrawl_deep_search.py`, `search_module.py`, `scrape_module.py`, `ai_extractor.py` to use unified executor
- Removed whole-company retry in `company_run.py`; added status mapping per §5.4
- Deleted dead `_batch_short_pages` from `ai_extractor.py`
- Dashboard label "Max Retries" → "Max Attempts"
- All tests pass (213 passed, 1 pre-existing failure)

Next action: **run doc sync check**, then merge after user confirmation.

Blocked: WI1 and WI2 need a user decision on spending.

Standing facts — do not re-derive, do not redo:

- The Korean Blacklist/Skip **executive** and **domain-evidence** reports are both
  COMPLETE for the verified window 22/05–14/07/2026. Detail in `work-items/`.
- Artifact `output/reports/blacklist-skip-domain-evidence-ko.html` is local only
  (`output/` is gitignored).
- If the domain-evidence report is regenerated, preserve the explicit `dauthau.info`
  Gemini Grounding provenance rule **first**.
- The replay estimate is a conservative Top-10 simulation, not an invoice total.

## Verification

Baseline: `venv/bin/python -m pytest tests/ -q` → **213 passed, 1 failed**
(`test_dashboard_import_filters.py::test_runner_restart_worker_starts_new_process_after_terminating_runtime_workers`,
`KeyError: 'stopped_pids'`, pre-existing). Doc gate: `bash scripts/check-doc-sync.sh` pending.