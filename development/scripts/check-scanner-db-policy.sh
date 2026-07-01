#!/usr/bin/env bash
#
# Scanner vuln-DB policy gate (M0b, D42). Fails CI if a *supported* scanner version would run a
# frozen or schema-incompatible vulnerability DB — so JAVV never silently ships a stale scanner.
# Facts come from versions.yaml `scanners.<s>.vuln_db` (not invented EOL dates); see that file.
#
#   development/scripts/check-scanner-db-policy.sh   # check (CI gate); non-zero on a frozen/stale pin
#
# Requires: yq.
set -euo pipefail
cd "$(dirname "$0")/../.."

V=versions.yaml
fail=0

# every supported version of a scanner (current + also_supported)
supported() {
  yq -r ".scanners.$1 | [.current] + (.also_supported // []) | .[]" "$V"
}

# lowest of two versions == the first arg  ⇒  ver >= floor
ver_ge() { [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" = "$2" ]; }

for scanner in $(yq -r '.scanners | keys | .[]' "$V"); do
  schema=$(yq -r ".scanners.$scanner.vuln_db.schema // \"\"" "$V")
  if [ -z "$schema" ]; then
    printf '  \033[1;31mMISSING\033[0m %s has no vuln_db.schema in %s\n' "$scanner" "$V"
    fail=1
    continue
  fi
  floor=$(yq -r ".scanners.$scanner.vuln_db.min_live_version // \"\"" "$V")
  for v in $(supported "$scanner"); do
    if [ -n "$floor" ] && ! ver_ge "$v" "$floor"; then
      printf '  \033[1;31mFROZEN\033[0m  %s %s < min_live_version %s — runs an older, frozen DB schema (below v%s); drop it\n' \
        "$scanner" "$v" "$floor" "$schema"
      fail=1
    else
      printf '  \033[1;32mok\033[0m     %-6s %-9s (DB schema v%s%s)\n' \
        "$scanner" "$v" "$schema" "${floor:+, live floor $floor}"
    fi
  done
done

if [ "$fail" -ne 0 ]; then
  echo
  echo "A supported scanner version would run a frozen/incompatible vuln DB. Fix versions.yaml."
  exit 1
fi
