#!/usr/bin/env bash
# commit-msg hook (AUDIT.md N2): reject locally what commitlint rejects in CI
# (commitlint.config.mjs = @commitlint/config-conventional + our 6 types), matching
# development/standards/git-workflow.md. Invoked by pre-commit with the commit-message file as $1.
# Cases: development/hooks/test-conventional-commit.sh.
set -euo pipefail

errors=()
first_line=$(head -1 "$1")

if ! grep -qE '^(feat|fix|chore|docs|test|refactor)(\(.+\))?!?: .+' <<<"$first_line"; then
  errors+=("must start with one of: feat|fix|chore|docs|test|refactor, e.g. 'feat(m1): hardened ingest'")
else
  subject=${first_line#*: }
  # commitlint bans sentence-, start-, pascal- and upper-case subjects; an uppercase first letter
  # is all of those in practice, identifiers included ('D21 …', 'OpenSearch …').
  [[ $subject =~ ^[A-Z] ]] && errors+=("subject must start lowercase, even for an identifier")
  [[ $subject == *. ]] && errors+=("subject must not end with a period")
fi
[ "${#first_line}" -gt 100 ] && errors+=("header is ${#first_line} chars, max 100")

# Body and footer lines, max 100 each. Git hands this hook the message before stripping comments,
# so '#' lines (its template) are skipped, and everything after the scissors line is the
# `commit -v` diff, not the message.
n=1
while IFS= read -r line || [ -n "$line" ]; do # the `||` keeps a last line with no newline
  n=$((n + 1))
  [[ $line == "# ------------------------ >8 ------------------------"* ]] && break
  [[ $line == "#"* ]] && continue
  [ "${#line}" -gt 100 ] && errors+=("line $n is ${#line} chars, max 100")
done < <(tail -n +2 "$1")

if [ "${#errors[@]}" -gt 0 ]; then
  echo "✗ Commit message rejected (CI's commitlint would fail it too):"
  printf '  - %s\n' "${errors[@]}"
  echo "  See development/standards/git-workflow.md"
  exit 1
fi
