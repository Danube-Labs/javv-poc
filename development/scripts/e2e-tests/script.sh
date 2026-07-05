#!/usr/bin/env bash
# JAVV end-to-end smoke (level 2: real scanners as host processes against k3d → backend).
# Risk-register #134 ingest smoke. NO CronJobs/Helm — that packaging is deferred to M10.
#
# PREREQUISITES (this script does NOT start them — it assumes they're up):
#   1. OpenSearch:  docker compose -f development/setup/opensearch-dev.yml up -d   (green)
#   2. Backend:     cd backend && JAVV_ENV=dev JAVV_BOOTSTRAP_ADMIN_USERNAME=admin \
#                     JAVV_BOOTSTRAP_ADMIN_PASSWORD=smoke-admin-pw \
#                     uv run uvicorn backend.main:app --port 8000
#                   (for a clean run, wipe first: docker compose ... down -v && up -d)
#   3. k3d cluster 'alpha' + trivy/grype on PATH.
#
# Writes per-component logs beside this script: backend.log is produced by the backend process
# itself; this script writes scanner-*.log, cluster.log, jobs.log, opensearch.log and refreshes
# results.md's underlying data. Run from anywhere.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
BACKEND="http://localhost:8000"
OS="http://localhost:9200"
CTX="k3d-alpha"
ADMIN_PW_INIT="smoke-admin-pw"
ADMIN_PW="smoke-admin-rotated-pw"
COOKIES="$ROOT/backend/cookies.txt"

say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31mFAIL: %s\033[0m\n' "$*" >&2; exit 1; }

# ---- 0. preflight -----------------------------------------------------------
say "preflight"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$OS")" = "200" ] || fail "OpenSearch not up at $OS"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$BACKEND/readyz")" = "200" ] || fail "backend not up at $BACKEND"
kubectl --context "$CTX" get ns kube-system >/dev/null 2>&1 || fail "k3d context $CTX unavailable"
command -v trivy >/dev/null || fail "trivy not on PATH"
command -v grype >/dev/null || fail "grype not on PATH"
echo "OK: OpenSearch, backend, k3d, trivy, grype"

# ---- 1. admin session (login + rotate must_change; idempotent across re-runs) ----
say "admin session"
if curl -s -c "$COOKIES" -X POST "$BACKEND/auth/login" -H 'content-type: application/json' \
     -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PW\"}" | grep -q '"username":"admin"'; then
  echo "logged in with rotated password"
else
  curl -s -c "$COOKIES" -X POST "$BACKEND/auth/login" -H 'content-type: application/json' \
    -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PW_INIT\"}" >/dev/null
  curl -s -b "$COOKIES" -c "$COOKIES" -X POST "$BACKEND/auth/password" -H 'content-type: application/json' \
    -d "{\"current_password\":\"$ADMIN_PW_INIT\",\"new_password\":\"$ADMIN_PW\"}" >/dev/null
  echo "logged in + rotated must_change password"
fi
curl -s -b "$COOKIES" "$BACKEND/auth/me" | grep -q '"must_change":false' || fail "session not usable"

# ---- 2. workloads: seed + a SECOND nginx tag --------------------------------
say "workloads (seed + second nginx tag)"
CLOG="$HERE/cluster.log"; : > "$CLOG"
{
  echo "########## workloads @ $(date -u +%FT%TZ) ##########"
  kubectl --context "$CTX" apply -f "$ROOT/development/setup/seed-vuln-workloads.yaml"
  kubectl --context "$CTX" -n javv-smoke get deploy nginx-second >/dev/null 2>&1 \
    || kubectl --context "$CTX" -n javv-smoke create deployment nginx-second --image=nginx:1.23.4
  for d in vuln-nginx vuln-python vuln-alpine nginx-second; do
    kubectl --context "$CTX" -n javv-smoke rollout status deployment/$d --timeout=120s
  done
  echo "=== running images (name | digest) ==="
  kubectl --context "$CTX" -n javv-smoke get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .status.containerStatuses[*]}{.image}{" | "}{.imageID}{"\n"}{end}{end}'
} | tee -a "$CLOG"

# ---- 3. cluster_id + per-scanner tokens -------------------------------------
say "cluster_id + tokens"
SCAN_CID="$(kubectl --context "$CTX" get ns kube-system -o jsonpath='{.metadata.uid}')"
echo "$SCAN_CID" | grep -Eq '^[a-z0-9-]{8,64}$' || fail "cluster_id shape invalid: $SCAN_CID"
echo "cluster_id: $SCAN_CID"
mint() { curl -s -b "$COOKIES" -X POST "$BACKEND/api/v1/admin/tokens" -H 'content-type: application/json' \
           -d "{\"cluster_id\":\"$SCAN_CID\",\"scanner\":\"$1\"}" | jq -r .token; }
TOK_TRIVY="$(mint trivy)"; TOK_GRYPE="$(mint grype)"
[ -n "$TOK_TRIVY" ] && [ -n "$TOK_GRYPE" ] || fail "token mint failed"

# ---- 4. scan cycles ---------------------------------------------------------
run_scanner() { # $1=scanner $2=token $3=logfile $4=label
  echo "########## $1 $4 @ $(date -u +%FT%TZ) ##########" >> "$3"
  ( cd "$ROOT/scanner" && KUBECONFIG="$HOME/.kube/config" JAVV_SCANNER="$1" \
      JAVV_BACKEND_URL="$BACKEND" JAVV_CLUSTER_ID="$SCAN_CID" JAVV_TOKEN="$2" \
      uv run python -m scanner ) >> "$3" 2>&1
  tail -1 "$3"
}
say "trivy cycle 1";  TLOG="$HERE/scanner-trivy.log"; : > "$TLOG"; run_scanner trivy "$TOK_TRIVY" "$TLOG" "cycle 1"
say "grype cycle 1";  GLOG="$HERE/scanner-grype.log"; : > "$GLOG"; run_scanner grype "$TOK_GRYPE" "$GLOG" "cycle 1"
say "trivy cycle 2 (idempotency/reconcile)"; run_scanner trivy "$TOK_TRIVY" "$TLOG" "cycle 2"

# ---- 5. verify --------------------------------------------------------------
say "verify"
curl -s -X POST "$OS/findings/_refresh" >/dev/null
count() { curl -s "$OS/findings/_count" -H 'content-type: application/json' \
  -d "{\"query\":{\"bool\":{\"filter\":[{\"term\":{\"cluster_id\":\"$SCAN_CID\"}},{\"term\":{\"scanner\":\"$1\"}}]}}}" | jq -r .count; }
T=$(count trivy); G=$(count grype)
echo "per-scanner findings (never summed):  trivy=$T  grype=$G"
[ "$T" -gt 0 ] && [ "$G" -gt 0 ] || fail "expected findings from both scanners"

echo "-- the 2 nginx tags (distinct digests) --"
curl -s "$OS/findings/_search" -H 'content-type: application/json' -d "{
  \"size\":0,\"query\":{\"bool\":{\"filter\":[{\"term\":{\"cluster_id\":\"$SCAN_CID\"}},
    {\"terms\":{\"image_digest\":[\"sha256:2bcabc23b45489fb0885d69a06ba1d648aeda973fae7bb981bafbb884165e514\",
                                  \"sha256:f5747a42e3adcb3168049d63278d7251d91185bb5111d2563d58729a5c9179b0\"]}}]}},
  \"aggs\":{\"d\":{\"terms\":{\"field\":\"image_digest\"},\"aggs\":{\"s\":{\"terms\":{\"field\":\"scanner\"}}}}}
}" | jq -r '.aggregations.d.buckets[] | .key as $d | .s.buckets[] | "  \($d[7:19])…  \(.key): \(.doc_count)"'

DIS=$(curl -s "$OS/findings/_count" -H 'content-type: application/json' \
  -d "{\"query\":{\"bool\":{\"filter\":[{\"term\":{\"cluster_id\":\"$SCAN_CID\"}},{\"term\":{\"disagree\":true}}]}}}" | jq -r .count)
echo "disagree=true findings (D5a): $DIS"
DELTAS=$(curl -s "$OS/javv-images-$SCAN_CID-*/_count" -H 'content-type: application/json' \
  -d '{"query":{"exists":{"field":"count_delta"}}}' | jq -r .count)
echo "image docs with count_delta (D5b): $DELTAS"
ING=$(curl -s "$OS/javv-scan-events-$SCAN_CID-*/_count" -H 'content-type: application/json' \
  -d '{"query":{"exists":{"field":"ingested_at"}}}' | jq -r .count)
echo "scan-events with server-stamped ingested_at (task F): $ING"
SO=$(curl -s "$OS/javv-scan-events-$SCAN_CID-*/_search" -H 'content-type: application/json' \
  -d '{"size":0,"query":{"term":{"scanner":"trivy"}},"aggs":{"m":{"max":{"field":"scan_order"}}}}' | jq -r '.aggregations.m.value')
echo "max trivy scan_order after 2 cycles (monotonic, expect >=2): $SO"

# ---- 6. background jobs -----------------------------------------------------
say "background jobs"
JLOG="$HERE/jobs.log"; : > "$JLOG"
{
  echo "########## jobs @ $(date -u +%FT%TZ) ##########"
  ( cd "$ROOT/backend" && JAVV_OPENSEARCH_URL="$OS" uv run python -m backend.jobs.staleness )
  ( cd "$ROOT/backend" && JAVV_OPENSEARCH_URL="$OS" uv run python -m backend.jobs.lifecycle )
} | tee -a "$JLOG"

# ---- 7. opensearch log snapshot --------------------------------------------
say "opensearch log snapshot"
OLOG="$HERE/opensearch.log"
{
  echo "########## OpenSearch container log @ $(date -u +%FT%TZ) ##########"
  docker logs javv-opensearch 2>&1 | tail -40
  echo; echo "########## index state ##########"
  curl -s "$OS/_cat/indices?v&s=index"
} > "$OLOG"

say "DONE — smoke green. See results.md and the per-component *.log files in this directory."
