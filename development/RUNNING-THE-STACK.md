# Running the JAVV stack by hand

A copy-paste runbook to bring up **everything built so far** on the dev VM and watch a real
scan flow end to end. Three paths:

- **Path A — backend only** (~5 min, no Kubernetes): OpenSearch + backend, then push a real
  envelope with `curl`. Proves ingest → findings → scan-events → triage → audit without scanners.
- **Path B — full stack** (adds k3d + Trivy/Grype): the real scanner discovers running pods and
  pushes for real. This is the end-to-end smoke from risk register #134.
- **Path F — the frontend** on top of Path A (or B): the Vue app against the local backend.

Every command is run from the repo root (`/home/sirbudd/Desktop/Github/javv-poc`) unless noted.
Lines starting `#` are comments; don't type them.

---

## 0. One-time prerequisites

Check your toolchain (all should print a version):

```bash
uv --version          # Python package/runner
docker ps             # Docker daemon reachable (if it needs sudo, add yourself to the docker group)
curl --version
jq --version          # for reading JSON responses (sudo apt install jq if missing)
# Path B only:
k3d version
kubectl version --client
trivy --version
grype version
```

If Docker needs `sudo`, either prefix the docker commands below or run
`sudo usermod -aG docker $USER && newgrp docker` once.

---

## Path A — backend only

### A1. Start OpenSearch

```bash
docker compose -f development/setup/opensearch-dev.yml up -d

# wait until it reports green (the compose file now disables the plugins that used to hang it)
until [ "$(curl -s localhost:9200/_cluster/health | jq -r .status)" = green ]; do
  echo "waiting for opensearch…"; sleep 3;
done
echo "opensearch is green"
```

### A2. Configure + start the backend

The backend reads `JAVV_*` env vars (see `docs/CONFIGURATION.md`). For a real run set a **token
pepper** (any non-empty secret) and a **bootstrap-admin password** so you get a login:

```bash
cd backend

export JAVV_OPENSEARCH_URL=http://localhost:9200
export JAVV_TOKEN_PEPPER='local-dev-pepper-change-me'      # peppers ingest tokens + session ids
export JAVV_BOOTSTRAP_ADMIN_USERNAME='admin'
export JAVV_BOOTSTRAP_ADMIN_PASSWORD='dev-admin-passphrase-12+'   # ≥12 chars (password policy)
export JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL=50   # default 10 starves rapid UI navigation/rigs with 429s

# create/upgrade every index + template (idempotent, versioned — MAPPING_VERSION 16 today)
uv run python -m backend.core.bootstrap

# start the API (foreground). It re-runs bootstrap, seeds the admin + default roles, then serves.
uv run uvicorn backend.main:app --port 8000
```

Leave that running. **Open a second terminal** for the rest (re-export `JAVV_OPENSEARCH_URL` there
if you use `python -m backend.*` tools). The API is now at http://localhost:8000 — live reference
at http://localhost:8000/docs.

### A3. Verify the backend is healthy

```bash
curl -s localhost:8000/healthz            # {"status":"ok"} — liveness, no OpenSearch needed
curl -s localhost:8000/readyz | jq        # {"status":"ready"} — 200 = OpenSearch reachable
```

### A4. Log in as the bootstrap admin (server-side session)

```bash
# login stores the httpOnly session cookie in cookies.txt; the admin is born must_change=true
curl -s -c cookies.txt -X POST localhost:8000/auth/login \
  -H 'content-type: application/json' \
  -d '{"username":"admin","password":"dev-admin-passphrase-12+"}' | jq

# must_change=true means the session can ONLY change the password until you do — so do it:
curl -s -b cookies.txt -c cookies.txt -X POST localhost:8000/auth/password \
  -H 'content-type: application/json' \
  -d '{"current_password":"dev-admin-passphrase-12+","new_password":"dev-admin-rotated-12+"}' | jq

curl -s -b cookies.txt localhost:8000/auth/me | jq   # now must_change=false, capabilities ["*"]
```

### A5. Mint an ingest token

Two ways — the admin API (needs the session from A4) or the CLI. The token must match the envelope
you'll push. The golden fixture's `cluster_id` is `0f0e6c4e-93f1-4b52-9f20-1234567890ab`, scanner
`trivy`:

```bash
export CID=0f0e6c4e-93f1-4b52-9f20-1234567890ab

# via the capability-gated API (raw token shown exactly once):
TOKEN=$(curl -s -b cookies.txt -X POST localhost:8000/api/v1/admin/tokens \
  -H 'content-type: application/json' \
  -d "{\"cluster_id\":\"$CID\",\"scanner\":\"trivy\"}" | jq -r .token)

# …or via the CLI (equivalent):
# TOKEN=$(cd backend && uv run python -m backend.core.tokens --cluster "$CID" --scanner trivy)

echo "token: $TOKEN"
```

### A6. Push a real envelope

The repo ships a real Trivy envelope (29 findings). Its `cluster_id`/`scanner` already match the
token. The ingest endpoint is `POST /api/v1/ingest/scan` (Bearer auth; plain JSON or gzip):

```bash
curl -s -X POST localhost:8000/api/v1/ingest/scan \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  --data-binary @backend/tests/fixtures/envelope-trivy-golden.json | jq
# → {"accepted":true,"findings":29,"commit":"<scan_run_id>"}
```

### A7. See the data land

```bash
# server-side counts come from OpenSearch aggregations, never the client.
# (If you've run the test suite against this same OpenSearch, `findings` holds accumulated
#  test data too — start from `down -v` in A1 for a clean count of exactly 29.)
curl -s "localhost:9200/findings/_count" -H 'content-type: application/json' \
  -d "{\"query\":{\"term\":{\"cluster_id\":\"$CID\"}}}" | jq        # 29 on a fresh volume

# the commit doc in the scan-events catalog (write alias → -000001 backing index)
curl -s "localhost:9200/javv-scan-events-$CID-*/_search?size=1" | jq '.hits.hits[0]._source | {scan_run_id, scan_order, total}'

# prometheus counters
curl -s localhost:8000/metrics | grep javv_ingest_
```

### A8. Exercise triage + the audit log

Pick one finding key and walk it through the state machine (needs `can_triage`; the admin has
`"*"`):

```bash
FK=$(curl -s "localhost:9200/findings/_search?size=1" -H 'content-type: application/json' \
  -d "{\"query\":{\"term\":{\"cluster_id\":\"$CID\"}}}" | jq -r '.hits.hits[0]._source.finding_key')

# acknowledge it
curl -s -b cookies.txt -X PATCH "localhost:8000/api/v1/findings/$FK/triage" \
  -H 'content-type: application/json' -d '{"state":"acknowledged"}' | jq '.finding.state'

# mark another not_affected with a CISA justification (needs the two-field pair)
curl -s -b cookies.txt -X PATCH "localhost:8000/api/v1/findings/$FK/triage" \
  -H 'content-type: application/json' \
  -d '{"state":"not_affected","vex_justification":"component_not_present"}' | jq '.finding | {state, vex_justification}'

# every action wrote one immutable audit row
curl -s "localhost:9200/system-audit-log-*/_search?size=5" -H 'content-type: application/json' \
  -d "{\"query\":{\"term\":{\"finding_key\":\"$FK\"}}}" | jq '.hits.hits[]._source | {action, field, old_value, new_value, revision}'
```

### A9. Run the background jobs by hand

These are k8s CronJobs in production; run them manually here (from `backend/`, with
`JAVV_OPENSEARCH_URL` exported):

```bash
cd backend
uv run python -m backend.jobs.staleness         # two-timer staleness sweep (D20)
uv run python -m backend.jobs.lifecycle         # rollover + per-cluster drop-whole-index retention
uv run python -m backend.jobs.findings_cleanup  # long-window findings cache cleanup (D37/M12)
uv run python -m backend.jobs.report_drain      # scheduled-export worker (leases pending reports)
uv run python -m backend.jobs.report_sweep      # report TTL + orphan-chunk reaper
uv run python -m backend.jobs.rebuild_state     # crash self-heal: decisions/presence/SLA-clock arms
```

Path A done — you've seen ingest → dedup/merge → commit catalog → triage → immutable audit, plus
the lifecycle jobs. **Teardown is section T.**

---

## Path B — full stack (real scanner against k3d)

Do Path A first (you need the backend up and a token). The scanner discovers **running pods** in a
Kubernetes cluster via its kubeconfig, so we need a k3d cluster with a workload, and Trivy/Grype
binaries on your PATH.

### B1. Create a k3d cluster and deploy something to scan

```bash
k3d cluster create alpha --servers 1 --agents 0 -p "8081:80@loadbalancer"
kubectl --context k3d-alpha get nodes           # Ready

# a couple of real images to discover + scan
kubectl --context k3d-alpha create deployment nginx --image=nginx:1.21.6
kubectl --context k3d-alpha create deployment redis --image=redis:7.0.0
kubectl --context k3d-alpha rollout status deployment/nginx
```

### B2. Point the scanner at the backend + cluster

The scanner needs: which scanner, the backend URL, a token, and (optionally) an explicit
`cluster_id`. If you don't set `JAVV_CLUSTER_ID` it derives one from the cluster's `kube-system`
namespace UID — but then the token's `cluster_id` must match that. Easiest is to **set both
explicitly** and mint a token for it:

```bash
# derive the cluster's real id (what the scanner would use), or pick your own 8–64 char slug
export SCAN_CID=$(kubectl --context k3d-alpha get namespace kube-system -o jsonpath='{.metadata.uid}')
echo "cluster_id: $SCAN_CID"

# mint a trivy token for THIS cluster_id (via the admin API from A4's cookies)
export SCAN_TOKEN=$(curl -s -b cookies.txt -X POST localhost:8000/api/v1/admin/tokens \
  -H 'content-type: application/json' \
  -d "{\"cluster_id\":\"$SCAN_CID\",\"scanner\":\"trivy\"}" | jq -r .token)
```

### B3. Run one Trivy scan cycle

```bash
cd scanner
KUBECONFIG=$HOME/.kube/config \
JAVV_SCANNER=trivy \
JAVV_BACKEND_URL=http://localhost:8000 \
JAVV_CLUSTER_ID=$SCAN_CID \
JAVV_TOKEN=$SCAN_TOKEN \
  uv run python -m scanner
```

What happens in one cycle: fetch scan-scope (`GET /api/v1/scan-scope`) → allocate `scan_order`
(`POST /api/v1/scan-runs`) → discover running pods → run `trivy` on each image → build a v4
envelope → push to `POST /api/v1/ingest/scan` for each. A failed image is logged and skipped, not fatal.

### B4. Run Grype too (per-scanner is sacred — never merged)

```bash
export SCAN_TOKEN_GRYPE=$(curl -s -b cookies.txt -X POST localhost:8000/api/v1/admin/tokens \
  -H 'content-type: application/json' \
  -d "{\"cluster_id\":\"$SCAN_CID\",\"scanner\":\"grype\"}" | jq -r .token)

cd scanner
KUBECONFIG=$HOME/.kube/config \
JAVV_SCANNER=grype JAVV_BACKEND_URL=http://localhost:8000 \
JAVV_CLUSTER_ID=$SCAN_CID JAVV_TOKEN=$SCAN_TOKEN_GRYPE \
  uv run python -m scanner
```

### B5. Observe the real scan

```bash
# findings for this real cluster, split by scanner (never summed)
for S in trivy grype; do
  echo -n "$S findings: "
  curl -s "localhost:9200/findings/_count" -H 'content-type: application/json' \
    -d "{\"query\":{\"bool\":{\"filter\":[{\"term\":{\"cluster_id\":\"$SCAN_CID\"}},{\"term\":{\"scanner\":\"$S\"}}]}}}" | jq -r .count
done

# run a SECOND trivy cycle, then check reconcile (fixed CVEs flip present=false)
cd scanner && KUBECONFIG=$HOME/.kube/config JAVV_SCANNER=trivy \
  JAVV_BACKEND_URL=http://localhost:8000 JAVV_CLUSTER_ID=$SCAN_CID JAVV_TOKEN=$SCAN_TOKEN \
  uv run python -m scanner
```

That's the full loop the k8s CronJobs will run on a schedule.

---

## Path F — the frontend

With the backend up (Path A) the Vue app runs against it via the vite dev proxy:

```bash
cd frontend
npm install          # first time only
npm run dev          # http://localhost:5173 — /api + /auth proxied to :8000
```

Log in with the bootstrap admin from A4. If the backend was started with the default PIT budget
(no `JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL=50`), rapid navigation will 429 — restart it with the
export from A2.

Two frontend gotchas that always bite:
- **After any backend contract change**: `(cd backend && uv run python -m backend.tools.export_openapi
  ../frontend/openapi.json) && (cd frontend && npm run gen:api)` — then **restart vite** (its module
  graph doesn't see new generated exports; imports 500 with "does not provide an export").
- **The dev backend has no `--reload`** — restart it after backend edits or new routes 404.

---

## R. Operational runbooks (where they live)

The authoritative procedure for each destructive/recovery operation is its module docstring + the
test that drills it — these can't drift from the code:

| Operation | Drive it | Drilled by |
|---|---|---|
| Snapshot / restore | Settings → Data & OpenSearch panel (`POST /api/v1/admin/snapshots` + `…/restore`) | `backend/tests/test_restore_drill.py` + `test_snapshot.py` |
| Rebuild state (crash self-heal) | `uv run python -m backend.jobs.rebuild_state` | `backend/tests/test_rebuild_presence.py` |
| Token rotation | Settings → Access & tokens (rotate = new secret, same scope), or `POST /api/v1/admin/tokens/{id}/rotate` | `backend/tests/test_token_admin.py` |
| Retention / rollover changes | Settings → Data & OpenSearch (applies at the next lifecycle sweep) | `backend/tests/test_lifecycle.py` |
| Findings cache cleanup | knob in the same panel; `uv run python -m backend.jobs.findings_cleanup` | `backend/tests/test_findings_cleanup.py` |

---

## T. Teardown

```bash
# stop the backend + vite: Ctrl-C in their terminals (or kill by PID from `ss -ltnp`, never pkill)
docker compose -f development/setup/opensearch-dev.yml down       # keep data
# docker compose -f development/setup/opensearch-dev.yml down -v   # wipe the data volume
k3d cluster delete alpha                                           # Path B only
rm -f backend/cookies.txt scanner/*.dead-letter.jsonl

# after running the backend test suite against this store: sweep the test residue
# (`nu-*`/`ext-*`/`0-list-*`/`u-*` users, `t-*` indices) — keep {admin, rig}; or `down -v` for a clean slate
```

---

## Troubleshooting

- **`readyz` returns 503 `degraded`** — OpenSearch isn't reachable; re-check A1 (`docker ps`,
  cluster health). The app stays up and degrades rather than crashing, by design.
- **Login 401 with the right password** — the cookie is `Secure`; over plain `http://` a browser
  won't send it back (localhost is exempted). `curl` with `-b/-c` is unaffected. This bites the UI
  on a non-TLS host (tracked for M10 in #134).
- **Ingest 403 `scope_mismatch`** — the token's `cluster_id`/`scanner` must equal the envelope's
  (SEC-3 binding). Mint a token for the exact pair you're pushing.
- **Ingest 401** — wrong/expired token, or `JAVV_TOKEN_PEPPER` differs between the process that
  minted the token and the running backend. Keep the pepper stable.
- **Scanner "scan scope unavailable — skipping cycle"** — the backend is unreachable from the
  scanner, or the token 401s the scope fetch. Fail-closed is intentional.
- **Scanner finds nothing** — no running pods matched the scope, or `kubectl get pods -A` is empty.
  Deploy something (B1).
- **Bootstrap admin didn't seed** — `JAVV_BOOTSTRAP_ADMIN_PASSWORD` was empty at startup (seed is
  skipped by design). Set it and restart the backend; it seeds once.
