# Stage 1 — Work Item 3: Retry Correctness

**Date:** 2026-08-17
**Branch:** `refactor/stage1-retry-executor`
**Goal:** Consolidate six competing retry owners into a single `RetryExecutor`, resolve the three-way 503 conflict, map operation-exhausted → `companies.status`, delete dead `_batch_short_pages`.

---

## Background

Currently six places in the code independently decide "call the API again", stacking on top of each other:
1. `src/connection_pool.py:75-78` — urllib3 `Retry(total=3, status_forcelist=[500,502,504])` — **missing 503**
2. `src/search_module.py:606-679` — own loop, `max_retries=3`, 429 → hard sleep 60s
3. `src/scrape_module.py:235` and `:462` — **two** separate loops, `max_retries=3`
4. `src/ai_extractor.py:371-545` — own loop + 503 branch sleeps 60s, ends returning `{"status":"failed","reason":"max_retries"}` — **error masquerading as valid dict**
5. `src/company_run.py:59` — retries **entire company**, `max_retries=2`
6. `src/rate_limiter.py` (`AdaptiveRateLimiter`) — **throttling only**: 429 → double delay; 403/503 → max delay + 5-min cooldown. **Keep as-is** — outside retry path.

Result: config says "retry 3 times" but reality fires 9 real requests (3 layers × 3 layers), costing 3× money with no visibility.

---

## Core Conflict: 503 Handled Three Ways Simultaneously

| Location | Behaviour |
|---|---|
| `ai_extractor.py` | Sleep 60s → retry |
| `connection_pool.py` | Skip (503 not in `status_forcelist`) |
| `rate_limiter.py` | Treat as overload → sleep 5 minutes |

All three run on the same event. Must unify to **one rule** and document in `MAP.md`.

---

## Files to Change

| File | Action |
|---|---|
| `src/v2/runtime/retry.py` | **CREATE NEW** — single retry executor: attempt counting, exponential backoff + jitter, stop decision, logging |
| `src/errors.py` | Classify errors: transient (retryable) vs permanent (futile) |
| `src/config.py:180` | Add `MAX_ATTEMPTS`. Keep `MAX_RETRIES` as deprecated alias, warn on use. **Semantics: `MAX_ATTEMPTS=3` = 1 initial + 2 retries**, not 4 |
| `src/connection_pool.py` | Disable HTTP-status retries; keep only connection pooling & timeouts |
| `src/firecrawl_deep_search.py` | Currently returns `[]` on 429/5xx/network error — must let error bubble up (`[]` mistaken for "0 results found") |
| `src/search_module.py` | Use shared error classification |
| `src/scrape_module.py` | Swallowing `RetryableError` in bare `except Exception` — remove |
| `src/gemini_quick_search.py` | Let transient errors bubble, don't return empty results |
| `src/ai_extractor.py` | Remove own retry loop after switching to executor |
| `src/company_run.py:57-81` | Remove whole-company retry at line 59; handle per §5.4 |
| `dashboard/frontend/assets/app.js` | Rename label "Max Retries" → "Max Attempts" |

---

## Operation-Exhausted → `companies.status` Mapping (Critical)

| Operation exhausted attempts | `companies.status` | Why |
|---|---|---|
| Search or scrape | `failed` | Re-run from start of that step. Existing `scraped_pages` rows kept & reused |
| AI extraction | **keep `ai_extract_pending`** | Scrape money already spent & data saved. **Never roll back past this checkpoint** — would lose paid-for data |
| `CriticalError` (401, 402, DB constraint) | Keep current checkpoint, stop entire batch | Same as V1, unchanged |

Every row above **must have a test verifying the final `companies.status` value**, not just that an exception was raised.

---

## Dead Code Removal

`src/ai_extractor.py:285` — `_batch_short_pages`, no callers. Delete at separate commit (commit 4). Verify with:
```bash
grep -rn "_batch_short_pages" src/ tests/ dashboard/
```

---

## Commit Plan

| # | Message | Content |
|---|---|---|
| 1 | `docs: record Stage 1 retry work item` | Create this file |
| 2 | `test: lock retry regressions` | Red tests — write first, watch fail, prove bug exists |
| 3 | `fix: retry failed API operations with exact attempts` | Code changes to make tests pass |
| 4 | `chore: delete the dead multi-page AI batching helper` | Remove `_batch_short_pages` |

Commit 4 separate from commit 3 so it can be reverted independently.

---

## Verification

```bash
# Full suite (baseline: 190 passed, 1 failed pre-existing)
venv/bin/python -m pytest tests/ -q

# Focused fast suite for this work item
venv/bin/python -m pytest -q tests/test_scrape_module.py tests/test_search_module.py tests/test_company_run.py tests/test_connection_pool.py tests/test_retry.py
```

> Note: `tests/test_rety.py` does not exist yet — created in commit 2.

Pre-commit gate:
```bash
bash scripts/check-doc-sync.sh
```

---

## No Real API Calls

This work item runs **100% on mocks**. Any real Firecrawl/Gemini call = violation.