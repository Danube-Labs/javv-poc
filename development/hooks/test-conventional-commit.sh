#!/usr/bin/env bash
# Cases for conventional-commit.sh. The hook's job is to reject locally what CI's commitlint
# rejects, and nothing it accepts, so both directions are pinned here. Run by pre-commit whenever
# development/hooks/ changes.
set -uo pipefail

HOOK="$(dirname "$0")/conventional-commit.sh"
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
fails=0
line100=$(printf 'x%.0s' $(seq 1 100))
line101="${line100}x"

check() { # expected(pass|fail), description, message
  printf '%s' "$3" > "$TMP"
  if bash "$HOOK" "$TMP" >/dev/null 2>&1; then got=pass; else got=fail; fi
  if [ "$got" != "$1" ]; then
    echo "✗ $2: expected $1, got $got"
    fails=$((fails + 1))
  fi
}

check pass "plain type"                 $'feat: add the thing'
check pass "scope + breaking marker"    $'refactor(api)!: drop the old route'
check pass "lowercase identifier"       $'chore(m5c): opensearch pin'
check pass "capital after first word"   $'fix(scope): some Message'
check pass "body line of exactly 100"   $'docs: wrap\n\n'"$line100"
check pass "footer line of exactly 100" $'docs: wrap\n\nbody\n\nRefs: '"${line100:6}"
check pass "long git template comment"  $'fix: x\n\n# '"$line101"
check pass "long diff after scissors"   $'fix: x\n\n# ------------------------ >8 ------------------------\n'"$line101"

check fail "unknown type"               $'feature: add the thing'
check fail "capitalised type"           $'Feat: add the thing'
check fail "empty subject"              $'feat: '
check fail "sentence-case subject"      $'feat: Add the thing'
check fail "identifier-first subject"   $'feat(m5c): D21 ruling applied'
check fail "upper-case subject"         $'feat: ADD'
check fail "subject ends with a period" $'feat: add the thing.'
check fail "header over 100"            "feat: ${line100}"
check fail "body line over 100"         $'docs: wrap\n\n'"$line101"
check fail "footer line over 100"       $'docs: wrap\n\nbody\n\nRefs: '"$line101"

if [ "$fails" -gt 0 ]; then
  echo "$fails case(s) failed"
  exit 1
fi
echo "all commit-message cases pass"
