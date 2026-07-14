#!/usr/bin/env bash
# Seed the CI route smoke's backend (#383, testing.md §4): bootstrap-admin login + must_change
# rotation, one ingest token, the GOLDEN trivy envelope (backend/tests/fixtures — the single
# source of truth for the ingest contract; when the contract changes, the fixture PR updates
# this seed for free), and the inventory-run commit so /images reads a committed run.
#
#   BACKEND=http://localhost:8000 ADMIN_PW_INIT=… ADMIN_PW=… ./development/scripts/seed-smoke.sh
#
# Mirrors development/e2e/smoke.sh §1/§3 (login/rotate/mint idiom) without k3d — the envelope
# replaces real scanners. Idempotent: re-runs re-push the same deterministic scan_run_id.
set -euo pipefail

BACKEND="${BACKEND:-http://localhost:8000}"
ADMIN_PW_INIT="${ADMIN_PW_INIT:?set ADMIN_PW_INIT}"
ADMIN_PW="${ADMIN_PW:?set ADMIN_PW}"
FIXTURE="$(dirname "$0")/../../backend/tests/fixtures/envelope-trivy-golden.json"
COOKIES="$(mktemp)"
trap 'rm -f "$COOKIES"' EXIT

fail() { echo "SEED FAILED: $1" >&2; exit 1; }

# 1. admin session (login + rotate must_change; idempotent across re-runs)
if curl -sf -c "$COOKIES" -X POST "$BACKEND/auth/login" -H 'content-type: application/json' \
     -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PW\"}" | grep -q '"username":"admin"'; then
  echo "seed: logged in with rotated password"
else
  curl -sf -c "$COOKIES" -X POST "$BACKEND/auth/login" -H 'content-type: application/json' \
    -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PW_INIT\"}" >/dev/null || fail "initial login"
  curl -sf -b "$COOKIES" -c "$COOKIES" -X POST "$BACKEND/auth/password" -H 'content-type: application/json' \
    -d "{\"current_password\":\"$ADMIN_PW_INIT\",\"new_password\":\"$ADMIN_PW\"}" >/dev/null || fail "rotate"
  echo "seed: logged in + rotated must_change password"
fi

# 2. ingest token for the fixture's cluster + scanner
CLUSTER_ID="$(jq -r .cluster_id "$FIXTURE")"
SCANNER="$(jq -r .scanner "$FIXTURE")"
TOKEN="$(curl -sf -b "$COOKIES" -X POST "$BACKEND/api/v1/admin/tokens" -H 'content-type: application/json' \
  -d "{\"cluster_id\":\"$CLUSTER_ID\",\"scanner\":\"$SCANNER\"}" | jq -r .token)"
[ -n "$TOKEN" ] && [ "$TOKEN" != null ] || fail "token mint"

# 3. the golden envelope + the inventory-run commit (status must come back committed)
curl -sf -X POST "$BACKEND/api/v1/ingest/scan" -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' --data-binary "@$FIXTURE" >/dev/null || fail "envelope ingest"
STATUS="$(curl -sf -X POST "$BACKEND/api/v1/inventory-runs" -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d "{\"scan_run_id\":\"$(jq -r .scan_run_id "$FIXTURE")\",\"expected_count\":1,\"started_at\":\"$(jq -r .last_seen_at "$FIXTURE")\"}" \
  | jq -r .status)"
[ "$STATUS" = committed ] || fail "inventory run not committed (status=$STATUS)"

echo "seed: cluster $CLUSTER_ID seeded — $(jq -r '.findings | length' "$FIXTURE") findings, inventory committed"
