# Implementation status

Last updated: 2026-08-14 +07
Overall state: no feature work in flight. Documentation rebuild and dead-code cleanup are merged.

Read first: `docs/architecture/MAP.md` (how the system works) and `docs/architecture/INDEX.md` (which contract doc covers what).

## Current handoff

All landed 2026-08-14 on `snapshot/ban-lasted-20260730`:

- Docs rebuilt from source — `MAP.md`, `INDEX.md`, `symbols.md`, `scripts/gen-symbols.sh`.
- `AGENTS.md` rewritten: two-file bootstrap, branch-per-code-change, docs in the same
  commit. `CLAUDE.md` imports it so Claude Code sees the rules at all.
- `scripts/check-doc-sync.sh` gained two guards (code changed on `main`; stale
  `symbols.md`), and `.claude/hooks/precommit-doc-sync.sh` blocks `git commit` when
  the gate fails.
- Serper removed — it was never wired up. Only `daily_quota.serper_used` remains,
  deliberately, so existing databases are not rewritten.
- Resume policy de-duplicated into `src/resume_policy.py`.
- `tests/manual/smoke_test.py` deleted; it had been broken since 2026-07-29. `pytest`
  no longer needs `--ignore`.

Next action: nothing queued. Blocked: nothing.


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

As of 2026-08-14: **190 passed, 1 failed**. The single failure is
`test_dashboard_import_filters.py::test_runner_restart_worker_starts_new_process_after_terminating_runtime_workers`
(`KeyError: 'stopped_pids'`), pre-existing. Any additional failure is yours.

Documentation gate: `bash scripts/check-doc-sync.sh`.
