#!/usr/bin/env bash
#
# The monitored cluster of CI's helm-app job, made while the job does other work (issue 780).
#
#   start <state dir, an absolute path>
#     Returns at once. In the background: creates the kind cluster `monitored` into its own
#     kubeconfig (kind would otherwise make it the current context under the steps still
#     running against the first cluster), then pulls on its node, from their registry, the
#     scanner images deploy/helm/javv-scanner renders with its ci/default-values.yaml, the
#     images the scanner pods then run. Its output goes to <state dir>/log, and its exit status
#     to <state dir>/status when it ends.
#
#   wait <state dir> [seconds]
#     Waits for start to end (600 seconds unless given), prints its log, and fails if it failed
#     or did not end in time. Then makes the monitored cluster the current context, as
#     `kind create cluster` does.
#
# Requires kind, docker and helm.
set -euo pipefail
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
cd "$(dirname "$0")/../.."

CLUSTER=monitored
CHART=deploy/helm/javv-scanner

images() {
  helm template s "$CHART" -f "$CHART/ci/default-values.yaml" |
    sed -nE 's/^ +image: "?([^"]+)"?$/\1/p' | sort -u
}

prepare() {
  local dir=$1 image
  kind create cluster --name "$CLUSTER" --kubeconfig "$dir/kubeconfig" --wait 2m
  for image in $(images); do
    echo "pulling $image on the monitored node"
    docker exec "$CLUSTER-control-plane" crictl pull "$image"
  done
}

start() {
  local dir=$1
  mkdir -p "$dir"
  rm -f "$dir/status" "$dir/status.tmp"
  # the status file appears whole and last (a rename), so its presence means the run ended
  nohup bash -c "\"$SELF\" prepare \"$dir\" >\"$dir/log\" 2>&1
    echo \$? >\"$dir/status.tmp\" && mv \"$dir/status.tmp\" \"$dir/status\"" >/dev/null 2>&1 &
  echo "making the monitored cluster in the background; its log is $dir/log"
}

wait_for() {
  local dir=$1 deadline=$((SECONDS + ${2:-600})) status
  until [ -f "$dir/status" ]; do
    if [ "$SECONDS" -ge "$deadline" ]; then
      cat "$dir/log" 2>/dev/null || true
      echo "FAIL: the monitored cluster was not ready in time" >&2
      exit 1
    fi
    sleep 2
  done
  cat "$dir/log"
  status=$(cat "$dir/status")
  if [ "$status" != 0 ]; then
    echo "FAIL: making the monitored cluster exited $status" >&2
    exit 1
  fi
  kind export kubeconfig --name "$CLUSTER"
}

command=${1:-}
shift || true
case "$command" in
  start) start "$@" ;;
  prepare) prepare "$@" ;;
  wait) wait_for "$@" ;;
  images) images ;;
  *) echo "usage: $0 start|wait <state dir> [seconds]" >&2; exit 2 ;;
esac
