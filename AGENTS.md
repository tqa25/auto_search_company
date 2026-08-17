# Agent instructions

Applies to every AI tool used on this repo (Claude Code, Codex, Cursor, …).

This file is the single source of the rules. Claude Code does not read
`AGENTS.md`, so the repo-root `CLAUDE.md` imports it with `@AGENTS.md`. Keep the
rules here; never copy them into `CLAUDE.md`, or the two will drift.

## 1. Session start — read exactly two files

1. `docs/architecture/MAP.md` — how the system works. Structural, stable.
2. `docs/implementation/STATUS.md` — where work stands right now. Volatile.

That is the whole bootstrap. **Do not bulk-read `src/`, `dashboard/`, or
`tests/` to "get oriented."** The map exists so that you don't have to. If the
map is wrong, fix the map — don't work around it by re-reading the codebase.

`docs/architecture/symbols.md` is a generated symbol → `file:line` jump table.
Open it when you need to locate something, not as part of startup.

## 2. Finding code — cheapest path first

In order. Stop as soon as you have what you need.

1. `docs/architecture/INDEX.md` — "what I want to change → which file"
2. `docs/architecture/symbols.md` — symbol → line number
3. `grep -n` for the specific identifier
4. `Read` with `offset`/`limit` around the hit

**Never read a file over 500 lines in full.** In this repo that means
`dashboard/app.py` (2,782), `src/database.py` (1,418), `src/excel_handler.py`
(867), `src/filter_module.py` (774), `src/search_module.py` (749),
`src/ai_extractor.py` (707), `src/scrape_module.py` (670), `src/pipeline.py`
(582). Locate the symbol, then read its range.

## 3. Source of truth, and what to distrust

`MAP.md` and `INDEX.md` are authoritative. If any other document contradicts
them, the other document is stale — **the code wins, then fix `MAP.md`.**

Treated as historical, not authoritative:
`PROJECT_HANDOVER.md`, `docs/v1-operational-audit*.md`,
`docs/v2-modular-refactor-plan*.md`, `docs/v2-stage1-*.md`.
These describe intent and history, some of it superseded. Read them only when
you specifically need business rationale, and never cite them over the code.

Do not import documentation, code, or agent instructions from V1 backups or
other repositories.

## 4. Talking to the user — gloss every technical term

The user works in Vietnamese. **Every English technical term gets an inline
Vietnamese explanation the first time it appears in a message**, in parentheses
right after the term. Explain the concept in plain words, not a dictionary
translation.

```
✅ checkpoint (điểm lưu tạm — trạng thái đã ghi xuống DB, chạy lại
   không phải làm lại từ đầu)
✅ race condition (lỗi tranh chấp — hai tiến trình cùng sửa một dữ liệu,
   kết quả phụ thuộc cái nào chạy trước)
✅ idempotent (chạy lại nhiều lần vẫn ra cùng kết quả, không nhân đôi dữ liệu)

❌ checkpoint          (bỏ trống, không giải thích)
❌ checkpoint (trạm kiểm soát)   (dịch từ điển, sai nghĩa trong ngữ cảnh)
```

Gloss **concepts**, not literals. These need no explanation because they are
names, not jargon: file paths, function and class names, variable names, CLI
flags, status values (`ai_extract_pending`), table and column names, error class
names. Glossing them adds noise.

Once a term is glossed in a message, use it bare for the rest of that message.

**Scope: conversation only.** Repository documents — `MAP.md`, `INDEX.md`,
`STATUS.md`, `symbols.md` — stay in English, and code comments follow the style
of the file they are in. There is deliberately **no Vietnamese `MAP.md`**;
maintaining two copies guarantees they drift apart.

## 5. Code changes go on a branch

Triggered by any change under `src/`, `dashboard/`, `scripts/`, or `tests/`.
Documentation-only changes do not need a branch — commit them where you are.

1. **Before touching anything**, run `git status`. If the working tree already
   has uncommitted changes that are not yours, stop and ask the user. Do not
   branch on top of someone else's unfinished work.
2. Record the current branch — this is the **base branch**, and it is the branch
   you will merge back into. It is not necessarily `main`.
3. Create the working branch from it: `<type>/<short-slug>`, where type is
   `fix`, `feat`, `refactor`, `perf`, or `chore`.
   Examples: `fix/serper-dead-path`, `refactor/dedupe-resume-status`.
4. Do the work. Commit in logical steps, not one giant commit at the end.
5. Run the tests (§6) and update the docs (§7). Both must be finished before
   you report back.
6. **Report to the user and stop.** State: what changed, which files, the exact
   test result, which docs were updated, and anything you could not verify.
7. **Merge only after the user explicitly confirms.** "Looks good", "ok", "merge
   it" — an explicit go-ahead. Silence, a new unrelated question, or the absence
   of objection is not confirmation.
8. On confirmation: merge into the base branch from step 2, then delete the
   working branch.

Never merge without confirmation. Never `git push` and never open a pull request
unless the user asks for it. If tests fail, report the failure — do not merge and
do not quietly fix around it.

## 6. Verifying

```
venv/bin/python -m pytest tests/ -q
```

Known-failing baseline (2026-08-14): **190 passed, 1 failed** —
`test_dashboard_import_filters.py::test_runner_restart_worker_starts_new_process_after_terminating_runtime_workers`.
Any additional failure is yours.

Use `replay_mode=True` to exercise pipeline logic against cached DB rows with
zero API calls before spending real quota. Note that `reparse_module` is **not**
a cache-only path — it spends Firecrawl credits.

## 7. Docs are part of the change, not a follow-up

Every code change updates its related documentation **in the same commit**. A
change is not finished when the code works; it is finished when the docs match
the code.

| What you changed | What you must update |
|---|---|
| A pipeline step, a `companies.status` value, strict-completion rules, a table or column, an entry point, an external service | `docs/architecture/MAP.md` — the affected section only |
| Added, moved, or renamed a public class or function | re-run `./scripts/gen-symbols.sh` |
| Which file owns a concern, or which test covers it | `docs/architecture/INDEX.md` |
| Anything at all | `docs/implementation/STATUS.md` — current state (§8) |
| Discovered the map was already wrong | fix `MAP.md` in the same commit, even if unrelated to your task |

Routine edits inside an existing function do not touch `MAP.md`. Use the table:
if your change is not in it, the map stays as it is.

`bash scripts/check-doc-sync.sh` enforces the floor — it fails when code changed
without any documentation change. Passing it is necessary, not sufficient: it
cannot tell whether what you wrote is *true*.

## 8. Definition of done

A code-changing session is incomplete until:

- Work happened on its own branch (§5).
- Tests were run, or `not run` is recorded with a reason.
- Docs were updated per §7.
- `bash scripts/check-doc-sync.sh` passes.
- The user was given the report from §5 step 6.

The gate is enforced, not merely requested: `.claude/hooks/precommit-doc-sync.sh`
is a `PreToolUse` hook that runs it before any `git commit` and blocks the commit
when it fails. The hook fails open — if it cannot run, the commit proceeds — so a
block always means the gate genuinely failed. Do not work around it by
disabling the hook; fix the documentation.

Never mark work complete merely because code was edited. Never claim a test
passed without having run it.

## 9. STATUS.md is a handoff note, not a changelog

Its job is to let anyone — human or agent — resume after a long gap without
re-deriving context. Therefore:

- **Replace its contents, don't append.** Keep it under ~40 lines.
- It answers only: what is in flight, what was just decided, what is the single
  next executable action, what is blocked.
- Finished work belongs in git history and `docs/implementation/work-items/`,
  not here.

If STATUS.md has grown past a screenful of scrollback, trim it before adding.

## 10. Keeping the map honest

The map is only worth its tokens while it is true. When you find `MAP.md`
disagreeing with the code:

1. Trust the code.
2. Correct `MAP.md` in the same commit.
3. If the drift was caused by a stale legacy doc, note it in §3 above.

Never add changelogs, dates, or session summaries to `MAP.md`. It describes the
system as it is now.
