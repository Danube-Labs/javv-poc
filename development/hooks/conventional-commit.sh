#!/usr/bin/env bash
# commit-msg hook (AUDIT.md N2): enforce the 6 conventional-commit types locally, matching
# commitlint in CI and development/standards/git-workflow.md. Invoked by pre-commit with the
# commit-message file as $1.
set -euo pipefail

first_line=$(head -1 "$1")
if ! grep -qE '^(feat|fix|chore|docs|test|refactor)(\(.+\))?!?: .+' <<<"$first_line"; then
  echo "✗ Commit message must start with one of: feat|fix|chore|docs|test|refactor"
  echo "  e.g. 'feat(M1): hardened ingest'  —  see development/standards/git-workflow.md"
  exit 1
fi
