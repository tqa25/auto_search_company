# Implementation status

Last updated: 2026-08-17 +07
Overall state: Stage 0 complete. Stage 1 work item 3 (retry) handed off for execution; work items 1 and 2 held pending user approval to spend.

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

Not being run in plan order; the first two work items are gated on spending decisions
only the user can make.

| Work item | State | Gate |
|---|---|---|
| WI1 — remove fixed waits (§4) | **held** | §4.1b A/B measurement spends real Firecrawl credit |
| WI2 — cache-hit + unique index (§5) | **held** | migration writes to `data/company_data.db` (1.98 GB); needs backup |
| WI3 — retry correctness (§6) | **handed off** | none — zero paid API, zero schema change |

WI3 handoff: `docs/implementation/work-items/2026-08-17-stage1-wi3-retry-handoff.md`.
Consolidate six competing retry owners into `src/v2/runtime/retry.py`, resolve the
three-way 503 conflict, map operation-exhausted → `companies.status`, delete dead
`_batch_short_pages`. Branch `refactor/stage1-retry-executor`, 4 commits, test-first.
Every `file:line` in it re-verified against live code 2026-08-17.

Next action: **verify WI3 when the executing agent reports back** — re-run the suite,
confirm all six retry owners were actually touched, confirm no real API call happened.
Do not accept the report at face value. Then decide with the user whether to unblock
WI1 or WI2.

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

Baseline: `venv/bin/python -m pytest tests/ -q` → **190 passed, 1 failed**
(`test_dashboard_import_filters.py::test_runner_restart_worker_starts_new_process_after_terminating_runtime_workers`,
`KeyError: 'stopped_pids'`, pre-existing). Doc gate: `bash scripts/check-doc-sync.sh` passed.
