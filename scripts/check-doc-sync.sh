#!/usr/bin/env bash
# Read-only documentation gate required by V2 plan §21.6.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

required_paths=(
  "AGENTS.md"
  "docs/architecture/MAP.md"
  "docs/architecture/INDEX.md"
  "docs/architecture/symbols.md"
  "docs/implementation/STATUS.md"
  "docs/implementation/work-items"
  "scripts/check-doc-sync.sh"
  "scripts/gen-symbols.sh"
)

for path in "${required_paths[@]}"; do
  if [[ ! -e "$path" ]]; then
    printf 'ERROR: required bootstrap path is missing: %s\n' "$path" >&2
    exit 1
  fi
done

for heading in "## Current handoff" "## Verification"; do
  if ! grep -Fqx "$heading" docs/implementation/STATUS.md; then
    printf 'ERROR: STATUS.md is missing required heading: %s\n' "$heading" >&2
    exit 1
  fi
done

if ! find docs/implementation/work-items -maxdepth 1 -type f -name '*.md' -print -quit | grep -q .; then
  printf 'ERROR: no work-item file exists in docs/implementation/work-items\n' >&2
  exit 1
fi

changed_paths="$({ git diff --name-only HEAD; git ls-files --others --exclude-standard; } | sort -u)"
code_changes="$(printf '%s\n' "$changed_paths" | grep -E '^(src|dashboard|scripts)/.*\.(py|js|mjs|ts|tsx|sh)$' | grep -v '^scripts/check-doc-sync\.sh$' || true)"

if [[ -n "$code_changes" ]]; then
  doc_changes="$(printf '%s\n' "$changed_paths" | grep -E '^docs/(architecture/|implementation/STATUS\.md)' || true)"
  if [[ -z "$doc_changes" ]]; then
    printf 'ERROR: code changed without matching architecture or STATUS documentation.\n' >&2
    printf '%s\n' "$code_changes" >&2
    exit 1
  fi
fi

# AGENTS.md §5 — code changes belong on a working branch, never directly on main.
if [[ -n "$code_changes" ]]; then
  current_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
  if [[ "$current_branch" == "main" ]]; then
    printf 'ERROR: code changed directly on main. AGENTS.md §5 requires a working branch.\n' >&2
    printf '  git switch -c fix/<short-slug>\n' >&2
    exit 1
  fi
fi

# AGENTS.md §7 — symbols.md is generated; it must not drift from the source tree.
# Generated to a temp file so this gate stays read-only.
if [[ -x scripts/gen-symbols.sh ]]; then
  expected="$(mktemp)"
  trap 'rm -f "$expected"' EXIT
  SYMBOLS_OUT="$expected" ./scripts/gen-symbols.sh >/dev/null
  if ! diff -q "$expected" docs/architecture/symbols.md >/dev/null 2>&1; then
    printf 'ERROR: docs/architecture/symbols.md is stale. Run ./scripts/gen-symbols.sh\n' >&2
    exit 1
  fi
fi

printf 'doc-sync check passed (read-only).\n'
