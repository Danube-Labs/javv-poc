#!/usr/bin/env bash
#
# Dependency vulnerability audit (issue 552), REPORT-ONLY: prints a Markdown report and always
# exits 0, per development/standards/dependency-policy.md (operator ruling: no gate for now).
# Production and dev-only dependencies are reported separately, because the fix deadlines differ.
#
#   development/scripts/dependency-audit.sh                          # report to stdout
#   development/scripts/dependency-audit.sh >> "$GITHUB_STEP_SUMMARY"  # the CI job
#
# Python: pip-audit over each uv lockfile export (backend, scanner, libs/javv-common).
# Frontend: npm audit over package-lock.json alone (no install needed).
# Requires: uv, npm, jq.
set -uo pipefail
cd "$(dirname "$0")/../.."

PIP_AUDIT_VERSION="${PIP_AUDIT_VERSION:-2.10.1}"
tmp=$(mktemp -d)
trap 'rm -r "$tmp"' EXIT

echo "## Dependency audit (report-only)"
echo
echo "Deadlines: [dependency-policy.md](development/standards/dependency-policy.md)."

python_group() {  # $1 = project dir, $2 = label, $3 = uv export group flag
  local dir="$1" label="$2" flag="$3" req="$tmp/req.txt" out
  echo
  echo "### $dir ($label)"
  echo
  if ! (cd "$dir" && NO_COLOR=1 uv export --frozen --no-hashes --no-emit-project --color never \
        --format requirements-txt "$flag" -q) | grep -v '^-e ' > "$req"; then
    echo "_Could not export the lockfile._"
    return
  fi
  if ! grep -q '^[A-Za-z]' "$req"; then
    echo "_No dependencies in this group._"
    return
  fi
  out=$(NO_COLOR=1 uvx -q "pip-audit@${PIP_AUDIT_VERSION}" -r "$req" --disable-pip --no-deps \
        --progress-spinner off -f markdown 2>/dev/null | awk 'NF && !seen[$0]++')
  if [ -n "$out" ]; then echo "$out"; else echo "No known vulnerabilities."; fi
}

for dir in backend scanner libs/javv-common; do
  python_group "$dir" "production" "--no-dev"
  python_group "$dir" "dev-only" "--only-dev"
done

npm_group() {  # $1 = label, $2.. = extra npm audit flags
  local label="$1"; shift
  local json
  echo
  echo "### frontend ($label)"
  echo
  json=$(cd frontend && npm audit --package-lock-only --json "$@" 2>/dev/null)
  if ! jq -e '.vulnerabilities' >/dev/null 2>&1 <<<"$json"; then
    echo "_npm audit gave no readable answer._"
    return
  fi
  if [ "$(jq '.vulnerabilities | length' <<<"$json")" = 0 ]; then
    echo "No known vulnerabilities."
    return
  fi
  echo "| Package | Severity | Affected | Fix available |"
  echo "|---|---|---|---|"
  jq -r '.vulnerabilities | to_entries | sort_by(.key)[] |
    "| \(.key) | \(.value.severity) | `\(.value.range)` | \(if .value.fixAvailable == false then "no" else "yes" end) |"' \
    <<<"$json"
}

npm_group "production" --omit=dev
npm_group "all, including dev"

exit 0
