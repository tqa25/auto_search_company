# Implementation status

Last updated: 2026-08-17 +07
Overall state: **Stage 0 baseline complete and accepted.** Ready to begin Stage 1.

Read first: `docs/architecture/MAP.md` (how the system works) and `docs/architecture/INDEX.md` (which contract doc covers what).

## Current handoff

Stage 0 (30-company baseline per V2 plan §3.0 / Stage 1 plan §3.0) is **complete**:

- Database unchanged: `data/company_data.db` (8,701 companies verified).
- Baseline file: `docs/implementation/work-items/stage0-baseline.md` — 30 companies, sampling method documented, group assignments explained.
- Data files:
  - `stage0_raw_query_results.json` — raw query results for all 30 companies (verified against live database, 8/30 random sample, 80 field checks, zero mismatches).
  - `docs/implementation/work-items/stage0-url-checklist.md` — all scraped URLs for manual inspection.
- Commits: `2bdbba7` finalized group B with high-confidence footer-misattribution cases (594, 1794, 1935, 2384 replacing 3, 4, 32, 39).

**Two known limitations (acceptable, not blockers):**

1. **Group A (same name, different province):** no genuinely different-province pair found in top results. The 4 sampled are same-address re-imports. One genuine pair exists (MINH TRÍ: id=758 Bắc Ninh, id=7290 Hà Nội) but was not substituted. If the sample needs strengthening later, can be replaced.
2. **Group B (footer misattribution):** the four companies now sampled have contact extracted from news articles demonstrably unrelated to the company (appointment news, personal-name pages, partial-name matches, tag pages). Contact misattribution is real — these are the intended high-confidence cases.

Next action: **Stage 1 work item 1 can start** (`fix/rip-out-serper` branch per `AGENTS.md` §5).

**Important:** Stage 1's first A/B measurement (plan §4.1b / §12.1: measure `waitFor` at 3000ms vs. 0) requires explicit **paid-API approval** before running. Nothing else in Stage 1 spends quota. Do not run that test gate without confirmation.

Blocked: nothing. Waiting on user approval to start Stage 1 work item 1.

Standing facts — do not re-derive, do not redo:

- The Korean Blacklist/Skip **executive** report and the Korean **domain-evidence**
  report are both COMPLETE for the verified production window 22/05–14/07/2026.
  Detail lives in `docs/implementation/work-items/`.
- Artifact: `output/reports/blacklist-skip-domain-evidence-ko.html` (local only;
  `output/` is gitignored, so it ships outside Git).
- If the domain-evidence report is ever regenerated, preserve the explicit
  `dauthau.info` Gemini Grounding provenance rule **first**.
- The replay estimate is a conservative Top-10 simulation, not an invoice total.

## Verification

Baseline: `venv/bin/python -m pytest tests/ -q`

Run 2026-08-17: **190 passed, 1 failed** — `test_dashboard_import_filters.py::test_runner_restart_worker_starts_new_process_after_terminating_runtime_workers`
(`KeyError: 'stopped_pids'`), pre-existing.

Documentation gate: `bash scripts/check-doc-sync.sh` — passed 2026-08-17.
