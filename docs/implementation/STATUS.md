# Implementation status

Last updated: 2026-08-17 +07
Overall state: no code work in flight. The two V2 plan documents were reconciled with the repository.

Read first: `docs/architecture/MAP.md` (how the system works) and `docs/architecture/INDEX.md` (which contract doc covers what).

## Current handoff

Landed 2026-08-17 on `snapshot/ban-lasted-20260730` (documentation only, no code touched):

- `docs/v2-modular-refactor-plan.en.md` and `docs/v2-stage1-critical-fixes-implementation-plan.md`
  revised. Both had been written on 2026-07-29 against a "copy V1 into a `version2`
  directory" model and a `STATUS.md` template that contradicts `AGENTS.md` §9.
- Process now defers to `AGENTS.md`: branch-based work in this repo, bootstrap docs
  already exist (repair-only), STATUS stays a short handoff note.
- Technical corrections: UNIQUE index must cover the **normalized** URL and the whole
  table must be normalized (§10.1 / Stage 1 §5.1); `filtered_links` + strict-completion
  fallout must be checked after migration (§10.2 / §5.5b); retry inventory is **six**
  owners — `src/rate_limiter.py` was missing (§11.1 / §6.2); `companies.status` after an
  operation exhausts its attempts is now defined (§11.2 / §6.6b); `waitFor → 0` needs a
  measured A/B gate first (§12.1 / §4.1b).
- All four V1 defects re-verified as still present; `src/v2/` does not exist. Duplicate
  counts re-measured: `data/company_data_1013_companies.db` has 19,069 duplicate groups
  / 19,946 excess rows. `data/company_data.db` (1.98 GB) not measured.

Next action: none queued. If Stage 1 is picked up, the first executable step is
Stage 0 — build the 30-company baseline into
`docs/implementation/work-items/stage0-baseline.md` (plan §3.0); Stage 1's replay
gate cannot conclude anything without it.

Blocked: the Vietnamese and Korean plan files still carry the superseded text
(sync debt recorded in `.en.md` §21.5).

Standing facts — do not re-derive, do not redo:

- The Korean Blacklist/Skip **executive** report and the Korean **domain-evidence**
  report are both COMPLETE for the verified production window 22/05–14/07/2026.
  Detail lives in `docs/implementation/work-items/`.
- Artifact: `output/reports/blacklist-skip-domain-evidence-ko.html` (local only;
  `output/` is gitignored, so it ships outside Git).
- If the domain-evidence report is ever regenerated, preserve the explicit
  `dauthau.info` Gemini Grounding provenance rule **first**. Grounding `source_url` is
  provenance-only: never label it Firecrawl scrape evidence or proof of a no-contact result.
- The replay estimate is a conservative Top-10 simulation and must **not** be treated
  as an invoice total.

## Verification

Baseline: `venv/bin/python -m pytest tests/ -q`

Run 2026-08-17: **190 passed, 1 failed** — `test_dashboard_import_filters.py::test_runner_restart_worker_starts_new_process_after_terminating_runtime_workers`
(`KeyError: 'stopped_pids'`), pre-existing. Any additional failure is yours.

Documentation gate: `bash scripts/check-doc-sync.sh` — passed 2026-08-17.
