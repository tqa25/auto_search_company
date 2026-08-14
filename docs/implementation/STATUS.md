# Implementation status

Last updated: 2026-08-14 +07
Overall state: no feature work in flight; the documentation rebuild just landed and is uncommitted.

Read first: `docs/architecture/MAP.md` (how the system works) and `docs/architecture/INDEX.md` (which contract doc covers what).

## Current handoff

In flight: the documentation rebuild itself, done 2026-08-14 — `MAP.md`, `INDEX.md`,
`symbols.md`, `scripts/gen-symbols.sh`, and the `AGENTS.md` rewrite. All present on disk
but still untracked/modified on `snapshot/ban-lasted-20260730`.

Next action: commit that rebuild (`docs/architecture/`, `docs/implementation/`,
`scripts/check-doc-sync.sh`, `scripts/gen-symbols.sh`, modified `AGENTS.md`). Nothing
else is queued. Blocked: nothing.

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
