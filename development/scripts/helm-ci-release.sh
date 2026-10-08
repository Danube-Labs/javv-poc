#!/usr/bin/env bash
#
# Prints the name of the one release of a chart in a namespace (issue 780). CI's helm-app job
# runs its checks on the release `ct install --skip-clean-up` keeps, which ct names after the chart
# plus a random suffix; the release is found by its chart, so the store's javv-opensearch release
# next to javv is not taken for it. Fails unless exactly one release of that chart is there.
#
#   development/scripts/helm-ci-release.sh <kube context> <namespace> <chart>
#
# Requires helm and jq.
set -euo pipefail

context=$1 ns=$2 chart=$3
releases=$(helm --kube-context "$context" -n "$ns" list -o json |
  jq -r --arg c "$chart" '.[] | select(.chart | test("^" + $c + "-[0-9]")) | .name')
if [ "$(grep -c . <<<"$releases")" != 1 ]; then
  echo "FAIL: want one $chart release in $ns, found: ${releases:-none}" >&2
  exit 1
fi
echo "$releases"
