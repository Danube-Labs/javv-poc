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
uv=$(yq -r '.toolchain.uv' "$V")
node=$(yq -r '.toolchain.node' "$V")
# Python has no versions.yaml entry: Renovate bumps the .python-version files and the Dockerfile
# ARG in one PR, so backend/.python-version is the reference the other copies must equal.
# --fix drops a Dockerfile image's digest (it belongs to the old tag); Renovate re-pins it.
python=$(cat backend/.python-version)

fail=0
src=$V  # what the DRIFT line names as the reference
# name | source-of-truth value | file | sed-match (extract) | sed-replace (for --fix)
check() {
  local name="$1" want="$2" file="$3" extract="$4" replace="$5"
  local have
  # Every match, not just the first: a file can repeat a pin (two OpenSearch services in ci.yml).
  # -z reads the file as one record so a pattern can span lines (the pre-commit hook's rev).
  have=$(grep -ozP "$extract" "$file" | tr '\0' '\n' | sort -u | paste -sd, || true)
  if [ "$have" = "$want" ]; then
    printf '  \033[1;32mok\033[0m   %-26s %s\n' "$name" "$want"
  elif [ "$FIX" -eq 1 ]; then
    sed -i -E "$replace" "$file"
    printf '  \033[1;33mfixed\033[0m %-26s %s -> %s\n' "$name" "$have" "$want"
  else
    printf '  \033[1;31mDRIFT\033[0m %-26s %s=%s but %s has %s\n' "$name" "$src" "$want" "$file" "$have"
    fail=1
  fi
}

check "Dockerfile.trivy ARG" "$trivy" scanner/Dockerfile.trivy \
  'ARG TRIVY_VERSION=\K[0-9.]+' "s/^ARG TRIVY_VERSION=.*/ARG TRIVY_VERSION=$trivy/"
check "Dockerfile.grype ARG" "$grype" scanner/Dockerfile.grype \
  'ARG GRYPE_VERSION=\K[0-9.]+' "s/^ARG GRYPE_VERSION=.*/ARG GRYPE_VERSION=$grype/"
check "Dockerfile.trivy uv image" "$uv" scanner/Dockerfile.trivy \
  'astral-sh/uv:\K[0-9.]+' "s#astral-sh/uv:[^ ]+#astral-sh/uv:$uv#"
check "Dockerfile.grype uv image" "$uv" scanner/Dockerfile.grype \
  'astral-sh/uv:\K[0-9.]+' "s#astral-sh/uv:[^ ]+#astral-sh/uv:$uv#"
check "opensearch dev compose" "$opensearch" development/setup/opensearch-dev.yml \
  'opensearchproject/opensearch:\K[0-9.]+' "s#opensearchproject/opensearch:[0-9.]+#opensearchproject/opensearch:$opensearch#"
check "opensearch CI service" "$opensearch" .github/workflows/ci.yml \
  'opensearchproject/opensearch:\K[0-9.]+' "s#opensearchproject/opensearch:[0-9.]+#opensearchproject/opensearch:$opensearch#"
check "opensearch clock-drift svc" "$opensearch" .github/workflows/clock-drift.yml \
  'opensearchproject/opensearch:\K[0-9.]+' "s#opensearchproject/opensearch:[0-9.]+#opensearchproject/opensearch:$opensearch#"
# Gate toolchain (D42 phase 2): ruff/pyright are pinned exactly in each pyproject.toml dev-deps
# (what CI runs via `uv run`); setup-dev.sh reads versions.yaml directly so it can't drift.
check "backend ruff pin" "$ruff" backend/pyproject.toml \
  'ruff==\K[0-9.]+' "s/ruff==[0-9.]+/ruff==$ruff/"
check "backend pyright pin" "$pyright" backend/pyproject.toml \
  'pyright==\K[0-9.]+' "s/pyright==[0-9.]+/pyright==$pyright/"
check "scanner ruff pin" "$ruff" scanner/pyproject.toml \
  'ruff==\K[0-9.]+' "s/ruff==[0-9.]+/ruff==$ruff/"
check "scanner pyright pin" "$pyright" scanner/pyproject.toml \
  'pyright==\K[0-9.]+' "s/pyright==[0-9.]+/pyright==$pyright/"
check "javv-common ruff pin" "$ruff" libs/javv-common/pyproject.toml \
  'ruff==\K[0-9.]+' "s/ruff==[0-9.]+/ruff==$ruff/"
check "javv-common pyright pin" "$pyright" libs/javv-common/pyproject.toml \
  'pyright==\K[0-9.]+' "s/pyright==[0-9.]+/pyright==$pyright/"
check "pre-commit ruff hook" "$ruff" .pre-commit-config.yaml \
  'ruff-pre-commit\s+rev: v\K[0-9.]+' "/ruff-pre-commit/{n;s/rev: v[0-9.]+/rev: v$ruff/}"
# Node is a manual major-only bump (no Renovate annotation in versions.yaml). frontend/package.json
# `engines` is a range, not a pin, so it isn't checked here.
check "ci.yml setup-node" "$node" .github/workflows/ci.yml \
  "node-version: '\K[0-9]+" "s/node-version: '[0-9]+'/node-version: '$node'/"
check "clock-drift setup-node" "$node" .github/workflows/clock-drift.yml \
  "node-version: '\K[0-9]+" "s/node-version: '[0-9]+'/node-version: '$node'/"
src=backend/.python-version
check "scanner .python-version" "$python" scanner/.python-version \
  '^\K[0-9.]+' "s/^[0-9.]+$/$python/"
check "Dockerfile.trivy python" "$python" scanner/Dockerfile.trivy \
  'FROM python:\K[0-9.]+(?=-slim)' "s/^FROM python:[^ ]+/FROM python:$python-slim/"
check "Dockerfile.grype python" "$python" scanner/Dockerfile.grype \
  'FROM python:\K[0-9.]+(?=-slim)' "s/^FROM python:[^ ]+/FROM python:$python-slim/"

if [ "$fail" -ne 0 ]; then
  echo
  echo "Pins drifted from versions.yaml. Run: development/scripts/check-versions.sh --fix"
  exit 1
fi
