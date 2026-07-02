#!/usr/bin/env bash
#
# Drift check (D42): assert every consumer's literal pin matches versions.yaml, the single source
# of truth for externally-owned tool/service versions. Consumers keep a literal pin so they work
# standalone (`docker build`, `docker compose up`); this guards against silent divergence.
# Renovate bumps versions.yaml → re-run this (`--fix`) to propagate, or CI fails until they match.
#
#   development/scripts/check-versions.sh        # check (CI gate); non-zero on drift
#   development/scripts/check-versions.sh --fix  # rewrite the consumer pins to match versions.yaml
#
# Requires: yq.
set -euo pipefail
cd "$(dirname "$0")/../.."

FIX=0
[ "${1:-}" = "--fix" ] && FIX=1

V=versions.yaml
trivy=$(yq -r '.scanners.trivy.current' "$V")
grype=$(yq -r '.scanners.grype.current' "$V")
opensearch=$(yq -r '.datastore.opensearch' "$V")
ruff=$(yq -r '.toolchain.ruff' "$V")
pyright=$(yq -r '.toolchain.pyright' "$V")

fail=0
# name | source-of-truth value | file | sed-match (extract) | sed-replace (for --fix)
check() {
  local name="$1" want="$2" file="$3" extract="$4" replace="$5"
  local have
  have=$(grep -oPm1 "$extract" "$file" || true)
  if [ "$have" = "$want" ]; then
    printf '  \033[1;32mok\033[0m   %-26s %s\n' "$name" "$want"
  elif [ "$FIX" -eq 1 ]; then
    sed -i -E "$replace" "$file"
    printf '  \033[1;33mfixed\033[0m %-26s %s -> %s\n' "$name" "$have" "$want"
  else
    printf '  \033[1;31mDRIFT\033[0m %-26s versions.yaml=%s but %s has %s\n' "$name" "$want" "$file" "$have"
    fail=1
  fi
}

check "Dockerfile.trivy ARG" "$trivy" scanner/Dockerfile.trivy \
  'ARG TRIVY_VERSION=\K[0-9.]+' "s/^ARG TRIVY_VERSION=.*/ARG TRIVY_VERSION=$trivy/"
check "Dockerfile.grype ARG" "$grype" scanner/Dockerfile.grype \
  'ARG GRYPE_VERSION=\K[0-9.]+' "s/^ARG GRYPE_VERSION=.*/ARG GRYPE_VERSION=$grype/"
check "opensearch dev compose" "$opensearch" development/setup/opensearch-dev.yml \
  'opensearchproject/opensearch:\K[0-9.]+' "s#opensearchproject/opensearch:[0-9.]+#opensearchproject/opensearch:$opensearch#"
check "opensearch CI service" "$opensearch" .github/workflows/ci.yml \
  'opensearchproject/opensearch:\K[0-9.]+' "s#opensearchproject/opensearch:[0-9.]+#opensearchproject/opensearch:$opensearch#"
# Gate toolchain (D42 phase 2): ruff/pyright are pinned exactly in each pyproject.toml dev-deps
# (what CI runs via `uv run`); setup-dev.sh reads versions.yaml directly so it can't drift.
check "scanner ruff pin" "$ruff" scanner/pyproject.toml \
  'ruff==\K[0-9.]+' "s/ruff==[0-9.]+/ruff==$ruff/"
check "scanner pyright pin" "$pyright" scanner/pyproject.toml \
  'pyright==\K[0-9.]+' "s/pyright==[0-9.]+/pyright==$pyright/"

if [ "$fail" -ne 0 ]; then
  echo
  echo "Pins drifted from versions.yaml. Run: development/scripts/check-versions.sh --fix"
  exit 1
fi
