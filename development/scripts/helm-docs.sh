#!/usr/bin/env bash
#
# Writes each chart's README.md under deploy/helm from its README.md.gotmpl and values.yaml, with
# the helm-docs version versions.yaml pins (issue 725). Only keys with a `# --` comment are listed.
#
#   development/scripts/helm-docs.sh           # write the READMEs
#   development/scripts/helm-docs.sh --check   # CI: fail if a README is not what it would write
#
# Requires docker and yq.
set -euo pipefail
cd "$(dirname "$0")/../.."

version=$(yq -r '.toolchain["helm-docs"]' versions.yaml)
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/deploy/helm:/helm" -w /helm \
  "jnorwood/helm-docs:v$version" --chart-search-root . --ignore-non-descriptions

if [ "${1:-}" = "--check" ]; then
  if ! git diff --exit-code -- 'deploy/helm/*/README.md'; then
    echo "A chart README is stale. Run development/scripts/helm-docs.sh and commit the result." >&2
    exit 1
  fi
fi
