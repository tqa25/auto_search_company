# Implementation status

Last updated: 2026-08-14 +07
Overall state: no feature work in flight. The documentation rebuild is committed and merged.

Read first: `docs/architecture/MAP.md` (how the system works) and `docs/architecture/INDEX.md` (which contract doc covers what).

## Current handoff

Landed 2026-08-14 on `snapshot/ban-lasted-20260730` via `chore/rebuild-codebase-docs`:
`MAP.md`, `INDEX.md`, `symbols.md`, `scripts/gen-symbols.sh`, the `AGENTS.md` rewrite,
and two new guards in `scripts/check-doc-sync.sh` (blocks code changes on `main`;
blocks a stale `symbols.md`).

Next action: nothing queued. Two known defects are documented in `MAP.md` §9 and are
worth picking up — the dead `serper_search` path (`dashboard/app.py:2489` imports a
module that does not exist) and the byte-identical duplication of
`suggest_resume_status` across `src/pipeline_worker.py:56` and `dashboard/app.py:958`.

Blocked: nothing.

Also open: `tests/manual/smoke_test.py` is dead — it reads a `Config.CONTACT_PATHS`
attribute that does not exist, so it exits before its first check. See `MAP.md` §10.
Its output directory is now gitignored.

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

Baseline: `venv/bin/python -m pytest tests/ -q --ignore=tests/manual`

As of 2026-08-14: **190 passed, 1 failed**. The single failure is
`test_dashboard_import_filters.py::test_runner_restart_worker_starts_new_process_after_terminating_runtime_workers`
(`KeyError: 'stopped_pids'`), pre-existing. Any additional failure is yours.

Documentation gate: `bash scripts/check-doc-sync.sh`.
