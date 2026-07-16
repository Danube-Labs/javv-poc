#!/usr/bin/env bash
# JAVV two-cluster isolation smoke (issue #431): a second k3d tenant (`beta`) is created, seeded
# and scanned, then every cross-bleed invariant from the #431 matrix is asserted — beta sees only
# its world, alpha's numbers don't move, shared digests stay per-tenant, and the token/edge
# guards (422/403/401) hold. Codifies the 2026-07-16 manual walk as a repeatable phase.
#
# PREREQUISITES (this script does NOT start them — same as smoke.sh):
#   1. OpenSearch:  docker compose -f development/setup/opensearch-dev.yml up -d   (green)
#   2. Backend:     cd backend && uvicorn with the dev bootstrap-admin env (see smoke.sh header)
#   3. k3d + trivy/grype on PATH. Cluster `alpha` is OPTIONAL — with it (and its data) the
#      shared-digest and alpha-unchanged assertions bite; without it they hold trivially.
#
# The beta cluster is created if absent and LEFT RUNNING (its data stays in OpenSearch either
# way). TWOC_TEARDOWN=1 deletes the k3d cluster at the end. Idempotent across re-runs
# (deterministic _id appends; scan_order is monotonic per token).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LOGS="$HERE/logs"; mkdir -p "$LOGS"
BACKEND="http://localhost:8000"
OS="http://localhost:9200"
BETA_CTX="k3d-beta"
ADMIN_PW_INIT="smoke-admin-pw"
ADMIN_PW="smoke-admin-rotated-pw"
COOKIES="$ROOT/backend/cookies.txt"
TWOC_TEARDOWN="${TWOC_TEARDOWN:-0}"

say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31mFAIL: %s\033[0m\n' "$*" >&2; exit 1; }

# ---- 0. preflight -----------------------------------------------------------
say "preflight"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$OS")" = "200" ] || fail "OpenSearch not up at $OS"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$BACKEND/readyz")" = "200" ] || fail "backend not up at $BACKEND"
command -v k3d >/dev/null || fail "k3d not on PATH"
command -v trivy >/dev/null || fail "trivy not on PATH"
command -v grype >/dev/null || fail "grype not on PATH"
echo "OK: OpenSearch, backend, k3d, trivy, grype"

# ---- 1. admin session (same init/rotated dance as smoke.sh) ------------------
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
api() { curl -s -b "$COOKIES" "$BACKEND$1"; }

# ---- 2. beta cluster (create if absent) + seed -------------------------------
say "beta cluster + seed"
CLOG="$LOGS/two-cluster.log"; : > "$CLOG"
{
  echo "########## beta @ $(date -u +%FT%TZ) ##########"
  k3d cluster list | grep -q '^beta ' || k3d cluster create beta --servers 1 --agents 0
  kubectl --context "$BETA_CTX" apply -f "$ROOT/development/setup/seed-beta-workloads.yaml"
  for ns in payments billing iot; do
    for d in $(kubectl --context "$BETA_CTX" -n "$ns" get deploy -o name 2>/dev/null); do
      kubectl --context "$BETA_CTX" -n "$ns" rollout status "$d" --timeout=300s
    done
  done
} | tee -a "$CLOG"

# ---- 3. tenant ids + per-scanner tokens --------------------------------------
say "tenant ids + tokens"
BETA_CID="$(kubectl --context "$BETA_CTX" get ns kube-system -o jsonpath='{.metadata.uid}')"
echo "$BETA_CID" | grep -Eq '^[a-z0-9-]{8,64}$' || fail "beta cluster_id shape invalid: $BETA_CID"
ALPHA_CID="$(kubectl --context k3d-alpha get ns kube-system -o jsonpath='{.metadata.uid}' 2>/dev/null || true)"
[ "$BETA_CID" != "$ALPHA_CID" ] || fail "beta and alpha share a cluster_id — tenancy is meaningless"
echo "beta:  $BETA_CID"
echo "alpha: ${ALPHA_CID:-<no alpha cluster — cross-tenant assertions hold trivially>}"
mint() { curl -s -b "$COOKIES" -X POST "$BACKEND/api/v1/admin/tokens" -H 'content-type: application/json' \
           -d "{\"cluster_id\":\"$BETA_CID\",\"scanner\":\"$1\"}" | jq -r .token; }
TOK_TRIVY="$(mint trivy)"; TOK_GRYPE="$(mint grype)"
[ -n "$TOK_TRIVY" ] && [ -n "$TOK_GRYPE" ] || fail "beta token mint failed"

# ---- 4. alpha baseline (BEFORE beta ingest — the un-moved goalpost) -----------
count() { curl -s "$OS/findings/_count" -H 'content-type: application/json' \
  -d "{\"query\":{\"bool\":{\"filter\":[{\"term\":{\"cluster_id\":\"$1\"}},{\"term\":{\"scanner\":\"$2\"}}]}}}" | jq -r .count; }
curl -s -X POST "$OS/findings/_refresh" >/dev/null
if [ -n "$ALPHA_CID" ]; then
  A_TRIVY_BEFORE=$(count "$ALPHA_CID" trivy); A_GRYPE_BEFORE=$(count "$ALPHA_CID" grype)
  echo "alpha baseline:  trivy=$A_TRIVY_BEFORE  grype=$A_GRYPE_BEFORE"
fi

# ---- 5. one cycle per scanner against beta ------------------------------------
# The scanner follows the kubeconfig's CURRENT context (no context env) — hand it a
# beta-only kubeconfig instead of flipping the global one (§B6).
BETA_KUBECONFIG="$(k3d kubeconfig write beta)"
run_scanner() { # $1=scanner $2=token
  echo "########## $1 beta cycle @ $(date -u +%FT%TZ) ##########" >> "$CLOG"
  ( cd "$ROOT/scanner" && KUBECONFIG="$BETA_KUBECONFIG" JAVV_SCANNER="$1" \
      JAVV_BACKEND_URL="$BACKEND" JAVV_CLUSTER_ID="$BETA_CID" JAVV_TOKEN="$2" \
      uv run python -m scanner ) >> "$CLOG" 2>&1
  tail -1 "$CLOG"
}
say "trivy beta cycle";  run_scanner trivy "$TOK_TRIVY"
say "grype beta cycle";  run_scanner grype "$TOK_GRYPE"
grep -q '"event": "cycle complete"' "$CLOG" || fail "no cycle-complete line in the beta scanner log"
grep -q '"dead_lettered": 0' "$CLOG" || fail "beta cycle dead-lettered envelopes"

# ---- 6. §1 server-read isolation ----------------------------------------------
say "§1 server reads: facet purity + alpha unchanged"
curl -s -X POST "$OS/findings/_refresh" >/dev/null
B_TRIVY=$(count "$BETA_CID" trivy); B_GRYPE=$(count "$BETA_CID" grype)
echo "beta per-scanner findings:  trivy=$B_TRIVY  grype=$B_GRYPE"
[ "$B_TRIVY" -gt 0 ] && [ "$B_GRYPE" -gt 0 ] || fail "expected beta findings from both scanners"

# beta's namespace facet is exactly its seeded world (+ k3s system namespaces, nothing of alpha's)
BETA_NS=$(api "/api/v1/findings/facets?cluster_id=$BETA_CID" | jq -r '[.facets.namespaces[].key] | sort | join(",")')
echo "beta namespaces: $BETA_NS"
for ns in payments billing iot; do
  echo "$BETA_NS" | grep -qw "$ns" || fail "beta namespace facet missing seeded ns '$ns'"
done
# alpha-only seed namespaces must NEVER appear under beta (shop/data/ops/legacy/javv-smoke)
for ns in shop ops legacy javv-smoke; do
  echo "$BETA_NS" | grep -qw "$ns" && fail "ALPHA namespace '$ns' leaked into beta's facets"
done

if [ -n "$ALPHA_CID" ]; then
  A_TRIVY_AFTER=$(count "$ALPHA_CID" trivy); A_GRYPE_AFTER=$(count "$ALPHA_CID" grype)
  [ "$A_TRIVY_AFTER" = "$A_TRIVY_BEFORE" ] && [ "$A_GRYPE_AFTER" = "$A_GRYPE_BEFORE" ] \
    || fail "alpha's counts moved during beta ingest (trivy $A_TRIVY_BEFORE→$A_TRIVY_AFTER, grype $A_GRYPE_BEFORE→$A_GRYPE_AFTER)"
  echo "alpha unchanged by beta ingest:  trivy=$A_TRIVY_AFTER  grype=$A_GRYPE_AFTER"
  # beta-only namespaces must not appear under alpha either
  ALPHA_NS=$(api "/api/v1/findings/facets?cluster_id=$ALPHA_CID" | jq -r '[.facets.namespaces[].key] | sort | join(",")')
  for ns in billing iot; do
    echo "$ALPHA_NS" | grep -qw "$ns" && fail "BETA namespace '$ns' leaked into alpha's facets"
  done
  echo "no beta namespaces in alpha's facets"
fi

# ---- 7. shared-digest trap: identical bits, per-tenant reads --------------------
# payments deliberately reuses alpha's image digests. Each tenant must serve its OWN result
# set for that digest; identical totals are expected (same bits), a combined read is the bug.
say "shared-digest trap"
if [ -n "$ALPHA_CID" ]; then
  SHARED=$(curl -s "$OS/findings/_search" -H 'content-type: application/json' -d "{
    \"size\":0,\"query\":{\"term\":{\"cluster_id\":\"$BETA_CID\"}},
    \"aggs\":{\"d\":{\"terms\":{\"field\":\"image_digest\",\"size\":50}}}}" \
    | jq -r '.aggregations.d.buckets[].key' | while read -r d; do
        A=$(curl -s "$OS/findings/_count" -H 'content-type: application/json' \
          -d "{\"query\":{\"bool\":{\"filter\":[{\"term\":{\"cluster_id\":\"$ALPHA_CID\"}},{\"term\":{\"image_digest\":\"$d\"}}]}}}" | jq -r .count)
        [ "$A" -gt 0 ] && { echo "$d"; break; }
      done)
  if [ -n "$SHARED" ]; then
    BT=$(api "/api/v1/findings?cluster_id=$BETA_CID&image_digest=$SHARED&size=1" | jq -r '.total.value')
    AT=$(api "/api/v1/findings?cluster_id=$ALPHA_CID&image_digest=$SHARED&size=1" | jq -r '.total.value')
    OS_B=$(curl -s "$OS/findings/_count" -H 'content-type: application/json' \
      -d "{\"query\":{\"bool\":{\"filter\":[{\"term\":{\"cluster_id\":\"$BETA_CID\"}},{\"term\":{\"image_digest\":\"$SHARED\"}}]}}}" | jq -r .count)
    echo "shared digest ${SHARED:7:12}…  beta api=$BT (store $OS_B) · alpha api=$AT"
    [ "$BT" -gt 0 ] && [ "$AT" -gt 0 ] || fail "shared digest not visible in both tenants"
    # the API total for beta must equal beta's OWN store count — never beta+alpha combined
    [ "$BT" -eq "$OS_B" ] || fail "beta API total ($BT) != beta-only store count ($OS_B) — combined read?"
  else
    echo "SKIPPED: no digest shared with alpha in this corpus (alpha unseeded/stale?)"
  fi
else
  echo "SKIPPED: no alpha cluster"
fi

# ---- 8. §3 edge guards: 422 / 403 / 401 -----------------------------------------
say "§3 edge guards"
[ "$(curl -s -o /dev/null -w '%{http_code}' -b "$COOKIES" "$BACKEND/api/v1/findings?size=1")" = "422" ] \
  || fail "findings without cluster_id did not 422"
echo "missing cluster_id: 422"

# a schema-valid envelope for the WRONG tenant, pushed with beta's token → 403, nothing ingested
ENV_ALPHA=$(jq -c --arg cid "${ALPHA_CID:-11111111-1111-4111-8111-111111111111}" '.cluster_id = $cid' \
  "$ROOT/backend/tests/fixtures/envelope-trivy-golden.json")
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BACKEND/api/v1/ingest/scan" \
  -H "authorization: Bearer $TOK_TRIVY" -H 'content-type: application/json' -d "$ENV_ALPHA")
[ "$CODE" = "403" ] || fail "cross-tenant envelope with beta token returned $CODE, want 403 (SEC-3)"
echo "cross-tenant envelope: 403"

ENV_BETA=$(jq -c --arg cid "$BETA_CID" '.cluster_id = $cid' \
  "$ROOT/backend/tests/fixtures/envelope-trivy-golden.json")
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BACKEND/api/v1/ingest/scan" \
  -H "authorization: Bearer $TOK_GRYPE" -H 'content-type: application/json' -d "$ENV_BETA")
[ "$CODE" = "403" ] || fail "trivy envelope with the grype token returned $CODE, want 403"
echo "cross-scanner token: 403"

CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BACKEND/api/v1/ingest/scan" \
  -H "authorization: Bearer 0000000000000000000000000000000000000000000" \
  -H 'content-type: application/json' -d "$ENV_BETA")
[ "$CODE" = "401" ] || fail "garbage token returned $CODE, want 401"
echo "garbage token: 401"

# ---- 9. §2 global surfaces: fleet adds, per-tenant reads stay pure ---------------
say "§2 global surfaces"
api "/api/v1/clusters" | jq -e '.clusters | map(.cluster_id) | index("'"$BETA_CID"'")' >/dev/null \
  || fail "clusters list missing beta"
if [ -n "$ALPHA_CID" ]; then
  api "/api/v1/clusters" | jq -e '.clusters | map(.cluster_id) | index("'"$ALPHA_CID"'")' >/dev/null \
    || fail "clusters list missing alpha"
fi
echo "clusters list: both tenants present"
# beta's provenance shows only beta's runs (a fresh beta has scan_order 1..n from ITS token)
api "/api/v1/scanners/provenance?cluster_id=$BETA_CID" \
  | jq -e '.scanners | length > 0' >/dev/null || fail "beta provenance empty"
echo "beta provenance: OK"

# ---- teardown (opt-in) ------------------------------------------------------------
if [ "$TWOC_TEARDOWN" = "1" ]; then
  say "teardown (TWOC_TEARDOWN=1)"
  k3d cluster delete beta
  echo "beta k3d cluster deleted (its OpenSearch data remains — a quiet tenant, by design)"
fi

say "DONE — two-cluster isolation smoke green. Log: $CLOG"
