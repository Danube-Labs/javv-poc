#!/usr/bin/env bash
# JAVV end-to-end smoke (level 2: real scanners as host processes against k3d → backend).
# Risk-register #134 ingest smoke. NO CronJobs/Helm — that packaging is deferred to M10.
#
# PREREQUISITES (this script does NOT start them — it assumes they're up):
#   1. OpenSearch:  docker compose -f development/setup/opensearch-dev.yml up -d   (green)
#   2. Backend:     cd backend && JAVV_ENV=dev JAVV_BOOTSTRAP_ADMIN_USERNAME=admin \
#                     JAVV_BOOTSTRAP_ADMIN_PASSWORD=smoke-admin-pw \
#                     uv run uvicorn backend.main:app --port 8000 \
#                       > development/e2e/logs/backend.log 2>&1
#                   (pipe to backend.log — the log-assertion phase reads it; JAVV_LOG_LEVEL=debug
#                    additionally surfaces every OpenSearch request, see docs/CONFIGURATION.md)
#                   (for a clean run, wipe first: docker compose ... down -v && up -d)
#   3. k3d cluster 'alpha' + trivy/grype on PATH.
#
# Writes per-component logs into ./logs/ (gitignored): backend.log is produced by the backend
# process itself; this script writes scanner-*.log, cluster.log, jobs.log, opensearch.log and
# refreshes results.md's underlying data. Run from anywhere.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LOGS="$HERE/logs"; mkdir -p "$LOGS"
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
CLOG="$LOGS/cluster.log"; : > "$CLOG"
{
  echo "########## workloads @ $(date -u +%FT%TZ) ##########"
  kubectl --context "$CTX" apply -f "$ROOT/development/setup/seed-vuln-workloads.yaml"
  kubectl --context "$CTX" -n javv-smoke get deploy nginx-second >/dev/null 2>&1 \
    || kubectl --context "$CTX" -n javv-smoke create deployment nginx-second --image=nginx:1.23.4
  # wait on EVERY seed namespace (the 2026-07-12 expansion added shop/data/ops/legacy)
  for ns in javv-smoke shop data ops legacy; do
    for d in $(kubectl --context "$CTX" -n "$ns" get deploy -o name 2>/dev/null); do
      kubectl --context "$CTX" -n "$ns" rollout status "$d" --timeout=300s
    done
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
run_scanner() { # $1=scanner $2=token $3=logfile $4=label [$5="EXTRA=env EXTRA2=env"]
  echo "########## $1 $4 @ $(date -u +%FT%TZ) ##########" >> "$3"
  ( cd "$ROOT/scanner" && env ${5:-} KUBECONFIG="$HOME/.kube/config" JAVV_SCANNER="$1" \
      JAVV_BACKEND_URL="$BACKEND" JAVV_CLUSTER_ID="$SCAN_CID" JAVV_TOKEN="$2" \
      uv run python -m scanner ) >> "$3" 2>&1
  tail -1 "$3"
}
say "trivy cycle 1";  TLOG="$LOGS/scanner-trivy.log"; : > "$TLOG"; run_scanner trivy "$TOK_TRIVY" "$TLOG" "cycle 1"
say "grype cycle 1";  GLOG="$LOGS/scanner-grype.log"; : > "$GLOG"; run_scanner grype "$TOK_GRYPE" "$GLOG" "cycle 1"
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

# ---- 6. reconcile / tombstone phase (#158) -----------------------------------
# The real present=false path: reconcile-on-commit is PER-DIGEST, so the flip needs the SAME
# digest re-scanned reporting fewer findings. `JAVV_TRIVY_SEVERITIES=CRITICAL` (#91 tuning) does
# exactly that — it mirrors the real trigger (a vuln-DB update dropping findings for an unchanged
# image). A disappeared image (e.g. a tag bump) is deliberately NOT reconciled — that's the
# staleness sweep's job (D20). A final full cycle proves re-appearance and keeps this idempotent.
say "reconcile phase: same digest, CRITICAL-only cycle → tombstones → full cycle → back"
present_trivy() { curl -s "$OS/findings/_count" -H 'content-type: application/json' \
  -d "{\"query\":{\"bool\":{\"filter\":[{\"term\":{\"cluster_id\":\"$SCAN_CID\"}},{\"term\":{\"scanner\":\"trivy\"}},{\"term\":{\"present\":$1}}]}}}" | jq -r .count; }
curl -s -X POST "$OS/findings/_refresh" >/dev/null
BASE_PRESENT=$(present_trivy true)
echo "baseline trivy present=true: $BASE_PRESENT"

run_scanner trivy "$TOK_TRIVY" "$TLOG" "cycle CRITICAL-only (reconcile repro)" "JAVV_TRIVY_SEVERITIES=CRITICAL"
curl -s -X POST "$OS/findings/_refresh" >/dev/null
NARROW_PRESENT=$(present_trivy true); TOMBSTONED=$(present_trivy false)
echo "after CRITICAL-only cycle: present=true $NARROW_PRESENT · present=false $TOMBSTONED"
[ "$NARROW_PRESENT" -lt "$BASE_PRESENT" ] || fail "reconcile did not shrink the present set"
[ "$TOMBSTONED" -gt 0 ] || fail "no findings flipped present=false"
WITH_RESOLVED=$(curl -s "$OS/findings/_count" -H 'content-type: application/json' \
  -d "{\"query\":{\"bool\":{\"filter\":[{\"term\":{\"cluster_id\":\"$SCAN_CID\"}},{\"term\":{\"scanner\":\"trivy\"}},{\"term\":{\"present\":false}},{\"exists\":{\"field\":\"resolved_at\"}}]}}}" | jq -r .count)
[ "$WITH_RESOLVED" = "$TOMBSTONED" ] || fail "tombstones missing resolved_at ($WITH_RESOLVED/$TOMBSTONED)"
echo "tombstones carry resolved_at: $WITH_RESOLVED/$TOMBSTONED"

run_scanner trivy "$TOK_TRIVY" "$TLOG" "cycle full (re-appearance)"
curl -s -X POST "$OS/findings/_refresh" >/dev/null
RESTORED=$(present_trivy true)
echo "after full cycle: present=true restored to $RESTORED (baseline $BASE_PRESENT)"
[ "$RESTORED" -eq "$BASE_PRESENT" ] || fail "re-appearance did not restore the present set"

# ---- 6b. log-content assertions (#158/#159): the pipeline itself is a contract ----
say "log assertions"
grep -q '"event": "ingest committed"' "$LOGS/backend.log" 2>/dev/null \
  || fail "backend.log has no 'ingest committed' JSON line (is the backend logging to it?)"
# grep -m1 (not `| head -1`): head closes the pipe early and grep dies with SIGPIPE, which `set -o
# pipefail` turns into a spurious failure once backend.log is large. -m1 stops grep itself, exit 0.
grep -m1 '"event": "ingest committed"' "$LOGS/backend.log" | jq -e .cluster_id >/dev/null \
  || fail "backend.log ingest line is not parseable JSON with cluster_id"
grep -q '"event": "scanning image"' "$TLOG" || fail "scanner log has no per-image progress lines"
grep -q '"event": "scan done"' "$TLOG" || fail "scanner log has no scan-done lines"
grep -q '"event": "cycle complete"' "$TLOG" || fail "scanner log has no cycle summary"
echo "backend JSON ingest lines + scanner per-image progress: present and parseable"

# ---- 7. background jobs -----------------------------------------------------
say "background jobs"
JLOG="$LOGS/jobs.log"; : > "$JLOG"
{
  echo "########## jobs @ $(date -u +%FT%TZ) ##########"
  ( cd "$ROOT/backend" && JAVV_OPENSEARCH_URL="$OS" uv run python -m backend.jobs.staleness )
  ( cd "$ROOT/backend" && JAVV_OPENSEARCH_URL="$OS" uv run python -m backend.jobs.lifecycle )
} | tee -a "$JLOG"

# ---- 8. read/report surface (#222 — major-audit phase 9) ---------------------
# Everything M5c→M7 built, exercised against the REAL corpus phases 1–7 produced. Idempotent:
# the decision is revoked in-phase, SLA is restored, the enqueued report is pending-only.
# Assertions are RELATIONS (>0, == between two views of one lens) — never absolute counts,
# the vuln-DB changes daily. Re-uses the phase-1 admin cookie jar (re-run phase 1 if standalone).
say "read/report surface"
api() { curl -s -b "$COOKIES" "$BACKEND$1"; }

# search: filtered first page + one cursor follow (proves PIT paging on real data)
PAGE=$(api "/api/v1/findings?cluster_id=$SCAN_CID&scanner=trivy&size=20")
ROWS=$(echo "$PAGE" | jq '.data | length')
[ "$ROWS" -gt 0 ] || fail "search returned no rows for trivy"
echo "$PAGE" | jq -e '.data | all(.scanner == "trivy")' >/dev/null || fail "scanner purity violated in search rows"
CURSOR=$(echo "$PAGE" | jq -r '.next_cursor // empty')
if [ -n "$CURSOR" ]; then
  api "/api/v1/findings?cluster_id=$SCAN_CID&cursor=$(printf %s "$CURSOR" | jq -sRr @uri)" \
    | jq -e '.data' >/dev/null || fail "cursor follow failed"
  echo "cursor follow: OK"
fi

# facets: per-scanner buckets present; counts are server-side
FACETS=$(api "/api/v1/findings/facets?cluster_id=$SCAN_CID")
echo "$FACETS" | jq -e '.facets.severity | length > 0' >/dev/null || fail "facets missing severity buckets"
# D46 (#274): bucket keys are the FULL-WORD canonical vocabulary, never crit/med or verbatim-case
echo "$FACETS" | jq -e '[.facets.severity[].key]
  | all(IN("critical","high","medium","low","negligible","unknown"))' >/dev/null \
  || fail "severity facet keys are not the D46 full-word vocabulary"
# ... and a full-word filter matches REAL ingested rows (the #274 regression: crit/med used to
# match nothing real, and only synthetic test seeds kept the old vocabulary green)
SEV=$(echo "$FACETS" | jq -r '.facets.severity[0].key')
SEV_ROWS=$(api "/api/v1/findings?cluster_id=$SCAN_CID&severity=$SEV&size=5" | jq '.data | length')
[ "$SEV_ROWS" -gt 0 ] || fail "severity=$SEV filter matched no real rows (D46/#274 regression)"
echo "severity vocabulary: OK ($SEV matches $SEV_ROWS real rows)"

# triage one real finding -> journaled
FK=$(echo "$PAGE" | jq -r '.data[0].finding_key')
curl -s -b "$COOKIES" -X PATCH "$BACKEND/api/v1/findings/$FK/triage" -H 'content-type: application/json' \
  -d '{"state":"acknowledged"}' | jq -e '.finding.state == "acknowledged" or .state == "acknowledged"' >/dev/null \
  || fail "triage PATCH failed for $FK"
curl -s -X POST "$OS/system-audit-log*/_refresh" >/dev/null
TRIAGED=$(curl -s "$OS/system-audit-log*/_count" -H 'content-type: application/json' \
  -d "{\"query\":{\"bool\":{\"filter\":[{\"term\":{\"entity_id\":\"$FK\"}}]}}}" | jq -r .count)
[ "$TRIAGED" -gt 0 ] || fail "triage left no audit row for $FK"
echo "triage journaled: $TRIAGED row(s) for $FK"

# decision round-trip: ignore_rule projects risk_accepted onto the CVE, revoke restores (D-run stamp
# in the justification identifies leftovers from a crashed run — decisions are immutable, revoke+new)
DCVE=$(echo "$PAGE" | jq -r '.data[1].cve_id')
DEC=$(curl -s -b "$COOKIES" -X POST "$BACKEND/api/v1/decisions" -H 'content-type: application/json' -d "{
  \"type\":\"ignore_rule\",\"cve_id\":\"$DCVE\",\"scope\":{\"namespaces\":[],\"images\":[]},
  \"apply_both_scanners\":true,\"justification\":\"smoke run $(date -u +%FT%TZ)\",\"cluster_id\":\"$SCAN_CID\"}")
DID=$(echo "$DEC" | jq -r '.decision.decision_id // empty')
[ -n "$DID" ] || fail "decision create failed: $DEC"
curl -s -X POST "$OS/findings/_refresh" >/dev/null
PROJ=$(curl -s "$OS/findings/_count" -H 'content-type: application/json' \
  -d "{\"query\":{\"bool\":{\"filter\":[{\"term\":{\"cluster_id\":\"$SCAN_CID\"}},{\"term\":{\"cve_id\":\"$DCVE\"}},{\"term\":{\"state\":\"risk_accepted\"}}]}}}" | jq -r .count)
[ "$PROJ" -gt 0 ] || fail "ignore_rule did not project risk_accepted onto $DCVE"
curl -s -b "$COOKIES" -X POST "$BACKEND/api/v1/decisions/$DID/revoke" | jq -e '.decision.revoked_at' >/dev/null || fail "revoke failed"
echo "decision round-trip on $DCVE: projected $PROJ finding(s), revoked"

# SLA: tweak -> read back -> restore (no residue). GET wraps as {"sla":{...}}; PUT takes the BARE
# policy (extra=forbid), and the knob is critical_days after the D46 hard rename (#274) — the old
# `crit_days` against the wrapper 422'd twice over, a live e2e gap the vocabulary rework left.
SLA0=$(api "/api/v1/settings/sla" | jq '.sla')
curl -s -b "$COOKIES" -X PUT "$BACKEND/api/v1/settings/sla" -H 'content-type: application/json' \
  -d "$(echo "$SLA0" | jq '.critical_days = 1')" >/dev/null
# critical_days is a float — it reads back as 1.0, so compare NUMERICALLY (jq ==), never a string match
api "/api/v1/settings/sla" | jq -e '.sla.critical_days == 1' >/dev/null || fail "SLA write did not read back"
curl -s -b "$COOKIES" -X PUT "$BACKEND/api/v1/settings/sla" -H 'content-type: application/json' -d "$SLA0" >/dev/null
echo "SLA round-trip: OK (restored)"

# trends + contributors (the smoke's own triage IS contributor data)
api "/api/v1/trends/scans?cluster_id=$SCAN_CID" | jq -e '.series' >/dev/null || fail "scans trend failed"
# trends/findings is the new/resolved burn-down twin — no .series (scans-only). Assert the twin
# series are real per-scanner objects, and that `new` actually recorded this run's ingest (non-empty)
api "/api/v1/trends/findings?cluster_id=$SCAN_CID" \
  | jq -e '(.new | type == "object") and (.resolved | type == "object") and (.new | length > 0)' >/dev/null \
  || fail "findings trend missing/empty new+resolved series"
api "/api/v1/contributors?cluster_id=$SCAN_CID" | jq -e . >/dev/null || fail "contributors failed"

# CSV export: row count == the same lens's search total; sanitizer holds on real data
CSV=$(api "/api/v1/findings/export.csv?cluster_id=$SCAN_CID&scanner=trivy")
CSV_ROWS=$(($(printf '%s\n' "$CSV" | wc -l) - 1))
T_NOW=$(count trivy)  # phase-5 helper; present=true is the export's implicit lens too
echo "csv rows: $CSV_ROWS (present trivy findings: $(present_trivy true))"
[ "$CSV_ROWS" -gt 0 ] || fail "CSV export empty"
printf '%s\n' "$CSV" | grep -qE '(^|,)"?[=+@]' && fail "CSV sanitizer let a formula-leading cell through"

# VEX per scanner (never merged): one scanner per document
api "/api/v1/findings/export.vex?cluster_id=$SCAN_CID&scanner=trivy" \
  | jq -e '.statements | length > 0' >/dev/null || fail "openvex export empty"

# M7 enqueue: pending doc + the public status view never leaks internals
REP=$(curl -s -b "$COOKIES" -X POST "$BACKEND/api/v1/reports" -H 'content-type: application/json' \
  -d "{\"cluster_id\":\"$SCAN_CID\",\"params\":{\"format\":\"csv\",\"scanner\":\"trivy\"}}")
RID=$(echo "$REP" | jq -r '.report_id // empty')
[ -n "$RID" ] || fail "report enqueue failed: $REP"
STATUS=$(api "/api/v1/reports/$RID")
[ "$(echo "$STATUS" | jq -r .status)" = "pending" ] || fail "report not pending: $STATUS"
echo "$STATUS" | jq -e 'has("params") or has("attempt_id") | not' >/dev/null || fail "report status leaks internals"
echo "report enqueued: $RID (pending; drain/download asserted when M7 slice 3 lands)"  # TODO(slice 3)

# metrics: ingest counters moved; the #220 series appear once that PR is deployed (guarded)
METRICS=$(curl -s "$BACKEND/metrics")
echo "$METRICS" | grep -q 'javv_ingest_accepted_total{scanner="trivy"}' || fail "/metrics missing ingest counters"
if echo "$METRICS" | grep -q 'javv_http_request_duration_seconds'; then
  echo "$METRICS" | grep -q 'route="unmatched"' && true
  echo "request histogram present (#220)"
fi
echo "read/report surface: ALL GREEN"

# ---- 8b. M8 surface: point-in-time + M8c/d/e reads (#249 gate) ----------------
# Everything M8b→M8e added, against the real corpus. The as-of probe is the load-bearing one:
# it proves D28 — a T captured before a state-changing rescan reconstructs the OLD world from the
# append logs (≤ T), so a later reconcile that shrinks present= is invisible at that T. Idempotent:
# a final full cycle restores the present set (same shape as section 6).
say "M8 surface: as-of-T, provenance, images, clusters, audit, views, ptype"
urlenc() { printf %s "$1" | jq -sRr @uri; }

# -- point-in-time reconstruction (D28/FR-23) --. Counts use the server-side `.total.value` (the real
# Trivy corpus is thousands of findings, far past any page cap), never a page-length count.
curl -s -X POST "$OS/findings/_refresh" >/dev/null
PRESENT_BEFORE=$(present_trivy true)
T_MARK="$(date -u +%FT%TZ)"; sleep 1
run_scanner trivy "$TOK_TRIVY" "$TLOG" "cycle CRITICAL-only (as-of repro)" "JAVV_TRIVY_SEVERITIES=CRITICAL"
curl -s -X POST "$OS/findings/_refresh" >/dev/null
PRESENT_NOW=$(present_trivy true)
[ "$PRESENT_NOW" -lt "$PRESENT_BEFORE" ] || fail "as-of setup: rescan did not shrink the present set"
# the CURRENT read (t=now) sees the shrunk set; the AS-OF read reconstructs the pre-shrink set.
asof_total() { api "/api/v1/findings?cluster_id=$SCAN_CID&scanner=trivy&present=true&size=1${1:+&as_of=$(urlenc "$1")}" | jq -r '.total.value'; }
ASOF_TOTAL=$(asof_total "$T_MARK")
NOW_TOTAL=$(asof_total)
echo "as-of $T_MARK present=$ASOF_TOTAL · now present=$NOW_TOTAL (pre-shrink baseline $PRESENT_BEFORE)"
[ "$ASOF_TOTAL" -eq "$PRESENT_BEFORE" ] || fail "as-of reconstruction ($ASOF_TOTAL) != pre-shrink present ($PRESENT_BEFORE) — D28 broken"
[ "$ASOF_TOTAL" -gt "$NOW_TOTAL" ] || fail "as-of read did not show the OLD (larger) present set"
api "/api/v1/findings?cluster_id=$SCAN_CID&scanner=trivy&present=true&size=20&as_of=$(urlenc "$T_MARK")" \
  | jq -e '.data | all(.scanner == "trivy")' >/dev/null || fail "as-of read violated scanner purity"
# determinism: the SAME past T, re-read, returns the SAME total even though the world moved on (D28)
[ "$(asof_total "$T_MARK")" -eq "$ASOF_TOTAL" ] || fail "as-of at a fixed T is not stable across re-reads"
run_scanner trivy "$TOK_TRIVY" "$TLOG" "cycle full (as-of restore)"
curl -s -X POST "$OS/findings/_refresh" >/dev/null
[ "$(present_trivy true)" -eq "$PRESENT_BEFORE" ] || fail "as-of phase did not restore the present set"
echo "point-in-time: OK (reconstructed old state, stable, restored)"

# -- provenance (M8c): catalog-first, exact scan_order (never a float-collapsed max, #257) --
PROV=$(api "/api/v1/scanners/provenance?cluster_id=$SCAN_CID")
echo "$PROV" | jq -e '.scanners | length > 0' >/dev/null || fail "provenance returned no scanners"
echo "$PROV" | jq -e '.scanners[] | select(.scanner=="trivy") | .last_run.scan_order >= 2' >/dev/null \
  || fail "provenance trivy last_run.scan_order not monotonic (expect >=2 after the cycles)"
echo "provenance: OK ($(echo "$PROV" | jq -r '.scanners | map(.scanner) | join(",")'))"

# -- images (M8c): inventory-committed running set; inventory:null is 'unknown', a valid answer --
IMG=$(api "/api/v1/images?cluster_id=$SCAN_CID")
echo "$IMG" | jq -e 'has("inventory") and has("images") and (.cluster_id=="'"$SCAN_CID"'")' >/dev/null \
  || fail "images endpoint shape wrong"
echo "images: OK (inventory=$(echo "$IMG" | jq -c '.inventory != null'), images=$(echo "$IMG" | jq '.images | length'))"

# -- audit read (M8c): cursor-paged over the REAL journal (this run's triage/decision/rename rows) --
AUD=$(api "/api/v1/audit?cluster_id=$SCAN_CID&size=5")
echo "$AUD" | jq -e '.data | length > 0' >/dev/null || fail "audit read returned no rows"
ACUR=$(echo "$AUD" | jq -r '.next_cursor // empty')
if [ -n "$ACUR" ]; then
  api "/api/v1/audit?cluster_id=$SCAN_CID&size=5&cursor=$(urlenc "$ACUR")" | jq -e '.data' >/dev/null \
    || fail "audit cursor follow failed"
  echo "audit: OK (paged, cursor follow OK)"
else
  echo "audit: OK ($(echo "$AUD" | jq '.data | length') rows, single page)"
fi

# -- clusters (M8c): registry + rename round-trip (journal-first + seq_no-CAS), then restore --
api "/api/v1/clusters" | jq -e '.clusters | map(.cluster_id) | index("'"$SCAN_CID"'")' >/dev/null \
  || fail "clusters list missing the smoke cluster_id"
CN0=$(api "/api/v1/clusters" | jq -r '.clusters[] | select(.cluster_id=="'"$SCAN_CID"'") | .cluster_name')
curl -s -b "$COOKIES" -X PUT "$BACKEND/api/v1/clusters/$SCAN_CID/name" -H 'content-type: application/json' \
  -d '{"cluster_name":"smoke-alpha"}' | jq -e '.cluster_name=="smoke-alpha"' >/dev/null || fail "cluster rename failed"
[ "$(api "/api/v1/clusters" | jq -r '.clusters[] | select(.cluster_id=="'"$SCAN_CID"'") | .cluster_name')" = "smoke-alpha" ] \
  || fail "cluster rename did not read back"
curl -s -X POST "$OS/system-audit-log*/_refresh" >/dev/null
[ "$(curl -s "$OS/system-audit-log*/_count" -H 'content-type: application/json' \
  -d '{"query":{"term":{"action":"cluster_rename"}}}' | jq -r .count)" -gt 0 ] || fail "cluster rename left no audit row"
# restore the original name (idempotent re-runs). CN0 may equal the id (no prior name) — that's fine.
curl -s -b "$COOKIES" -X PUT "$BACKEND/api/v1/clusters/$SCAN_CID/name" -H 'content-type: application/json' \
  -d "$(jq -nc --arg n "$CN0" '{cluster_name:$n}')" >/dev/null
echo "clusters: OK (rename journaled + restored)"

# -- saved views (M8e): create -> read -> deep-link params -> PATCH (CAS) -> delete, all journaled --
VBODY='{"name":"smoke-view","description":"e2e","preset":{"severity":["critical","high"],"scanner":"trivy","present":true}}'
VID=$(curl -s -b "$COOKIES" -X POST "$BACKEND/api/v1/views" -H 'content-type: application/json' -d "$VBODY" | jq -r '.view_id // empty')
[ -n "$VID" ] || fail "view create failed"
api "/api/v1/views" | jq -e '.views | map(.view_id) | index("'"$VID"'")' >/dev/null || fail "created view not listed"
# the preset is a SearchFilters mirror — its severity list is the D46 full-word vocabulary and drives a real query
VSEV=$(api "/api/v1/views" | jq -r '.views[] | select(.view_id=="'"$VID"'") | .preset.severity[0]')
[ "$VSEV" = "critical" ] || fail "view preset severity not stored as the full-word canonical (got: $VSEV)"
curl -s -b "$COOKIES" -X PATCH "$BACKEND/api/v1/views/$VID" -H 'content-type: application/json' \
  -d '{"description":"e2e-updated"}' | jq -e '.description=="e2e-updated"' >/dev/null || fail "view PATCH failed"
curl -s -b "$COOKIES" -o /dev/null -w '%{http_code}' -X DELETE "$BACKEND/api/v1/views/$VID" | grep -q 204 || fail "view DELETE not 204"
api "/api/v1/views" | jq -e '.views | map(.view_id) | index("'"$VID"'") | not' >/dev/null || fail "view still present after delete"
echo "saved views: OK (create/read/patch/delete round-trip)"

# -- ptype facet (M8d): real trivy/grype output populates os + real ecosystems; missing -> "unknown" --
PTF=$(api "/api/v1/findings/facets?cluster_id=$SCAN_CID")
echo "$PTF" | jq -e '.facets.ptype | length > 0' >/dev/null || fail "facets missing ptype buckets"
echo "$PTF" | jq -e '[.facets.ptype[].key] | index("os")' >/dev/null \
  || fail "ptype facet has no 'os' bucket (trivy os-pkgs should produce it)"
echo "ptype facet: OK ($(echo "$PTF" | jq -r '[.facets.ptype[].key] | join(",")'))"

# ---- 8c. D46 vocabulary end-to-end (#274): crit->critical, at the wire and every read ----------
# The rework moved the severity VALUE vocabulary to six full words while the count COLUMN names kept
# the short form (crit/med — a wire/mapping constant, not a vocabulary). This section proves both
# halves survive a REAL scanner round-trip, and that the SLA clock — which silently matched nothing
# real before #274 — now actually ticks. (The facet KEY check already ran in section 8's facets.)
say "D46 vocabulary end-to-end"

# -- wire check: finding docs carry a full-word severity_canonical; scan-events carry short columns --
curl -s -X POST "$OS/findings/_refresh" >/dev/null
BADCANON=$(curl -s "$OS/findings/_search" -H 'content-type: application/json' -d "{
  \"size\":0,\"query\":{\"bool\":{\"filter\":[{\"term\":{\"cluster_id\":\"$SCAN_CID\"}},
    {\"terms\":{\"severity_canonical\":[\"crit\",\"med\",\"moderate\"]}}]}}}" | jq -r '.hits.total.value')
[ "$BADCANON" = "0" ] || fail "found $BADCANON finding docs with a SHORT severity_canonical (D46 regression)"
GOODCANON=$(curl -s "$OS/findings/_search" -H 'content-type: application/json' -d "{
  \"size\":0,\"query\":{\"bool\":{\"filter\":[{\"term\":{\"cluster_id\":\"$SCAN_CID\"}},
    {\"terms\":{\"severity_canonical\":[\"critical\",\"high\",\"medium\",\"low\",\"negligible\",\"unknown\"]}}]}}}" | jq -r '.hits.total.value')
[ "$GOODCANON" -gt 0 ] || fail "no finding docs carry a full-word severity_canonical"
# the count COLUMNS on scan-events keep the short form (COUNT_COLUMN shim) — assert the mapping held
curl -s "$OS/javv-scan-events-$SCAN_CID-*/_search" -H 'content-type: application/json' \
  -d '{"size":1,"query":{"term":{"scanner":"trivy"}}}' \
  | jq -e '.hits.hits[0]._source | has("crit") and has("med") and has("total")' >/dev/null \
  || fail "scan-events counts lost the short COUNT_COLUMN names (crit/med)"
echo "wire: OK (severity_canonical full words · counts short columns)"

# -- SLA overdue regression (#274): the buried days_for bug — no real finding EVER went overdue since
# M5d because days_for keyed on canonical words while callers passed verbatim severities (a real
# "Critical"/"CRITICAL" resolved to None → never overdue). The proof is that days_for RESOLVES for a
# real critical at all: a near-zero critical_days tips every freshly-ingested critical overdue (their
# first_seen is minutes old, so ~0.09s of budget is already blown). Restored immediately after.
SLA_SAVE=$(api "/api/v1/settings/sla" | jq '.sla')
curl -s -b "$COOKIES" -X PUT "$BACKEND/api/v1/settings/sla" -H 'content-type: application/json' \
  -d "$(echo "$SLA_SAVE" | jq '.critical_days = 0.000001')" >/dev/null
CRIT_PAGE=$(api "/api/v1/findings?cluster_id=$SCAN_CID&severity=critical&present=true&size=100")
OVERDUE=$(echo "$CRIT_PAGE" | jq '[.data[] | select(.overdue == true)] | length')
CRIT_TOTAL=$(echo "$CRIT_PAGE" | jq '.data | length')
curl -s -b "$COOKIES" -X PUT "$BACKEND/api/v1/settings/sla" -H 'content-type: application/json' -d "$SLA_SAVE" >/dev/null
if [ "$CRIT_TOTAL" -gt 0 ]; then
  [ "$OVERDUE" -gt 0 ] || fail "no critical finding went overdue under a 1-day SLA — the #274 days_for bug is back"
  echo "SLA overdue: OK ($OVERDUE/$CRIT_TOTAL critical findings overdue under a 1-day policy)"
else
  echo "SLA overdue: SKIPPED (no present critical trivy findings in this corpus today)"
fi

# -- export vocabulary: CSV + VEX carry full-word severities, never the short form --
# Capture the DISTINCT severity values into a var and test that (never a `... | grep -q && fail`
# pipeline: under pipefail an early-closing grep can SIGPIPE `sort`, making `&& fail` short-circuit
# and SILENTLY MISS a real violation). Here grep reads the whole column, so a bad token is caught.
CSV_D46=$(api "/api/v1/findings/export.csv?cluster_id=$SCAN_CID&scanner=trivy")
HDR="${CSV_D46%%$'\n'*}"
# CSV header uses BARE column names (severity), not quoted — match accordingly
SEV_COL=$(printf '%s\n' "$HDR" | tr ',' '\n' | grep -nx 'severity' | cut -d: -f1 || true)
[ -n "$SEV_COL" ] || fail "CSV export has no severity column to check (header: $HDR)"
SEV_VALS=$(printf '%s\n' "$CSV_D46" | tail -n +2 | cut -d, -f"$SEV_COL" | tr -d '"' | sort -u)
BAD_SEV=$(printf '%s\n' "$SEV_VALS" | grep -iE '^(crit|med|moderate)$' || true)
[ -z "$BAD_SEV" ] || fail "CSV severity column carries a short/legacy token (D46): $BAD_SEV"
echo "CSV severity values: $(printf '%s' "$SEV_VALS" | tr '\n' ' ')"
echo "export vocabulary: OK"
echo "D46 vocabulary: ALL GREEN"

# ---- 8d. invariant: a COMPLETED read must delete its PIT (finally-delete) --------
# NOT a raw "0 PITs" check: a cursor-paginated read the client ABANDONS mid-walk (e.g. the search /
# audit first-page reads above) legitimately holds its PIT until keep_alive (2m) — the server can't
# force-delete a PIT the client may still resume. That's inherent to pagination, not a leak. The real
# invariant is that a read which RUNS TO COMPLETION releases its PIT at once. So we snapshot the count,
# drive two completing reads (contributors = a full PIT walk; facets), and assert they add nothing.
say "PIT-leak invariant (completed reads must finally-delete)"
pit_count() { curl -s "$OS/_search/point_in_time/_all" 2>/dev/null | jq -r '.pits | length' 2>/dev/null || echo 0; }
PIT_BEFORE=$(pit_count)
api "/api/v1/contributors?cluster_id=$SCAN_CID" >/dev/null   # opens + finally-deletes a full PIT walk
api "/api/v1/findings/facets?cluster_id=$SCAN_CID" >/dev/null
PIT_AFTER=$(pit_count)
[ "$PIT_AFTER" -le "$PIT_BEFORE" ] \
  || fail "a completed read leaked $((PIT_AFTER - PIT_BEFORE)) PIT(s) — a finally-delete is missing (before=$PIT_BEFORE after=$PIT_AFTER)"
echo "completed reads leaked 0 PITs (before=$PIT_BEFORE after=$PIT_AFTER; abandoned-cursor PITs drain at keep_alive)"

# ---- 9. opensearch log snapshot --------------------------------------------
say "opensearch log snapshot"
OLOG="$LOGS/opensearch.log"
{
  echo "########## OpenSearch container log @ $(date -u +%FT%TZ) ##########"
  docker logs javv-opensearch 2>&1 | tail -40
  echo; echo "########## index state ##########"
  curl -s "$OS/_cat/indices?v&s=index"
} > "$OLOG"

say "DONE — smoke green. See results.md and the per-component logs in ./logs/."
