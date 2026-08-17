# Implementation status

Last updated: 2026-08-17 +07
Overall state: Stage 0 baseline data verified correct; table had transcription errors, now fixed. Two open items need a user decision before Stage 0 counts as fully done.

Read first: `docs/architecture/MAP.md` (how the system works) and `docs/architecture/INDEX.md` (which contract doc covers what).

## Current handoff

Stage 0 executed by another agent (Google Antigravity) per
`docs/implementation/work-items/2026-08-17-stage0-baseline-handoff.md`. Verified this
session, independently, against the live database (not just trusted the file):

- DB untouched: `data/company_data.db` mtime/size unchanged from before execution.
  30 unique `company_id`, no duplicates.
- `stage0_raw_query_results.json` re-queried live for 8/30 random companies (80 field
  comparisons) — **zero mismatches**. This file is trustworthy.
- `docs/implementation/work-items/stage0-baseline.md`'s hand-written table had 3 real
  transcription errors (wrong company name for id=2604, truncated name for id=6, wrong
  `business_status=NULL` for 4 group-A companies that are actually "Đang hoạt động").
  **Fixed**: table mechanically regenerated from the verified JSON; correction is
  noted inline in the file itself.

Two open items the executing agent flagged and could not resolve on its own — need a
user call before treating Stage 0 as fully accepted:

1. Nhóm A (same name, different province) — no true different-province pair exists in
   the top 50 duplicate names; the 4 sampled are same-address re-imports of the same
   company. If a genuinely different-province pair is required, needs manual search.
2. Nhóm B (news-domain footer) — companies picked by a hardcoded domain list
   (cafef, tuoitre, kenh14, vietnamnet); not confirmed by eye that the scraped URL is
   actually a misattributed footer contact vs. a legitimate news mention.

Also worth noting, not blocking: all 30 sampled companies have `status=done` — no
mid-flight-failure sample exists in this baseline.

Next action: **user decides** whether items 1–2 need patching before Stage 1 starts,
or whether the baseline is good enough as-is. Once accepted, Stage 1 work item 1 can
start — its `waitFor` A/B measurement (plan §4.1b / §12.1) needs separate paid-API
approval; nothing else in Stage 1 does.

Blocked: nothing — waiting on user decision, not stuck.

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
