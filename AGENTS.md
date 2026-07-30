# Agent instructions

## Source of truth

Start with `PROJECT_HANDOVER.md` when receiving the repository. Read `docs/v1-operational-audit.md` when interpreting V1 code or data.

Read `docs/v2-modular-refactor-plan.md` before changing application code. The Vietnamese plan governs intended V2 business behaviour. Use `docs/v2-modular-refactor-plan.en.md` as the condensed agent specification and `docs/v2-stage1-critical-fixes-implementation-plan.md` for Stage 1 execution.

Do not use documentation, code, graphs, or agent instructions from V1 backups or other repositories.

## Mandatory self-bootstrap

Before the first code edit in any task authorized to add, edit, or delete code:

1. Read §21.6 of `docs/v2-modular-refactor-plan.md`.
2. Check for:
   - `docs/architecture/INDEX.md`
   - `docs/implementation/STATUS.md`
   - `docs/implementation/work-items/`
   - `scripts/check-doc-sync.sh`
3. Automatically create or repair missing parts according to §21.6.
4. Do not overwrite existing content or invent completed work.
5. Verify repository reality with `git status`, relevant code/migrations, and tests actually run.
6. Create or claim the current work item before editing code.

For read-only explanation, review, or diagnosis, report a missing bootstrap but do not create files.

If bootstrap cannot be completed safely, do not change code. Record the blocker when possible and ask the user.

## Definition of done

A code-changing session is incomplete until:

- Relevant tests have been run, or `not run` is recorded with a reason.
- Matching module contracts and architecture index entries are updated.
- `docs/implementation/STATUS.md` records changed behaviour, files added/edited/deleted, exact verification results, blockers, working-tree warnings, and one executable next action.
- The current work-item file records acceptance evidence and final state.
- `scripts/check-doc-sync.sh` passes.

Never mark work complete merely because code was edited.
