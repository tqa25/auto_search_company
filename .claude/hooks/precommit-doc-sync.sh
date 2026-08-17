#!/usr/bin/env bash
# PreToolUse hook (Bash): refuse `git commit` when the documentation gate fails.
#
# AGENTS.md §8 requires scripts/check-doc-sync.sh to pass before work is done.
# This turns that rule from something an agent is asked to remember into
# something it cannot skip.
#
# Contract:
#   stdin  — hook JSON, {"tool_input": {"command": "..."}}
#   exit 0 — allow the command
#   exit 2 — block it; the JSON on stdout explains why
#
# Fails open: if anything about the check itself is broken or missing, the
# commit is allowed. A blocked commit must mean the gate genuinely failed,
# never that the hook misfired.

INPUT=$(cat)

# Extract the command. Node handles shell escaping correctly; the global GSD
# hooks on this machine use the same approach, so node is a safe dependency.
CMD=$(printf '%s' "$INPUT" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{process.stdout.write(JSON.parse(d).tool_input?.command||'')}catch{}})" 2>/dev/null)

[ -n "$CMD" ] || exit 0

# Is this a git commit? Walk tokens rather than regexing "git commit", so that
# `git -C path commit`, `/usr/bin/git commit` and `FOO=1 git commit` are caught,
# and `git log --grep="commit"` is not.
printf '%s' "$CMD" | node -e "
let d='';
process.stdin.on('data', c => d += c);
process.stdin.on('end', () => {
  // Split on shell separators so 'git add . && git commit -m x' is seen.
  const segments = d.split(/(?:&&|\|\||[;|&\n])/);
  const isCommit = segments.some(seg => {
    const tokens = seg.trim().split(/\s+/).filter(Boolean);
    let i = 0;
    while (i < tokens.length && /^[A-Za-z_][A-Za-z0-9_]*=/.test(tokens[i])) i++;   // env prefix
    if (i >= tokens.length) return false;
    const cmd = tokens[i].replace(/^.*\//, '');                                     // strip path
    if (cmd !== 'git') return false;
    i++;
    while (i < tokens.length && tokens[i].startsWith('-')) {
      if (tokens[i] === '-C' || tokens[i] === '-c') i++;                            // flag takes a value
      i++;
    }
    return tokens[i] === 'commit';
  });
  process.exit(isCommit ? 0 : 1);
});
" 2>/dev/null || exit 0

# Only guard this repository, and only when the gate actually exists.
[ -f scripts/check-doc-sync.sh ] || exit 0

if ! OUTPUT=$(bash scripts/check-doc-sync.sh 2>&1); then
  REASON=$(printf '%s' "$OUTPUT" | tr '\n' ' ' | sed 's/"/\\"/g')
  printf '{"decision": "block", "code": "DOC_SYNC_FAILED", "reason": "AGENTS.md §8: the documentation gate must pass before committing. scripts/check-doc-sync.sh said: %s"}\n' "$REASON"
  exit 2
fi

exit 0
