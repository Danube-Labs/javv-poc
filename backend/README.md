# JAVV backend

FastAPI (async) + `AsyncOpenSearch`. Ingests the M0 scanner envelope and serves the read/reporting
API — every number comes from an OpenSearch aggregation (server-side; no raw findings to the client).
Bolt: **M1** (`development/bolts/M1-backend-skeleton/`, #23).

## Layout (STACK-BEST-PRACTICES §1)
```
src/backend/
  core/       settings · lifespan (single AsyncOpenSearch client) · errors (problem-details envelope)
              · bootstrap (versioned dynamic:false indexes/templates — INDEX-MAP_v4 is the source of truth)
  routers/    HTTP layer — health now; ingest + read APIs next
  main.py     app factory (create_app)
```
Bootstrap the indexes against a running OpenSearch: `uv run python -m backend.core.bootstrap`
(idempotent + versioned; M1 scope = `findings`, `system-tokens`, and the `javv-scan-events-*` /
`javv-images-*` templates — watermarks are M3's, occurrences M8a's, audit-log M5a's).

**When it runs:** manual for now; the observability slice wires it into **app startup** (lifespan:
ping → bootstrap → serve; unreachable = fail fast) — safe every boot because unchanged versions are
a no-op and the concurrent-create race is handled (the Kibana pattern: version-gated boot-time
migration). Additive changes = edit INDEX-MAP + bootstrap.py, bump `MAPPING_VERSION`; a field
**type change** is a reindex migration — never automatic.

## Manual end-to-end test (the full pipeline, verified 2026-07-02)

Real scanner → token-authed ingest → OpenSearch. Prereqs: dev OpenSearch on :9200, k3d `alpha`
up with the `javv-smoke` seed workloads (`kubectl apply -f development/setup/seed-vuln-workloads.yaml`).

```bash
# 1. bootstrap the indexes (idempotent)
cd backend && uv run python -m backend.core.bootstrap

# 2. start the backend
uv run uvicorn backend.main:app --port 8000    # (or & for background)

# 3. mint an ingest token for the cluster (raw token prints ONCE — only its hash is stored)
CID=$(kubectl --context k3d-alpha get namespace kube-system -o jsonpath='{.metadata.uid}')
TOKEN=$(uv run python -m backend.core.tokens --cluster "$CID" --scanner trivy)

# 4. run a real scan cycle against the cluster, pushing to the backend
cd ../scanner
JAVV_SCANNER=trivy JAVV_BACKEND_URL=http://localhost:8000 JAVV_TOKEN="$TOKEN" \
  uv run python -m scanner
# → "trivy: scanned 8 image(s) — 8 delivered, 0 dead-lettered"

# 5. see the findings (severity agg; lc normalizer folds scanner casing)
curl -s 'localhost:9200/findings/_search?size=0' -H 'Content-Type: application/json' \
  -d "{\"query\":{\"term\":{\"cluster_id\":\"$CID\"}},
       \"aggs\":{\"sev\":{\"terms\":{\"field\":\"severity\"}}}}" | jq '.aggregations.sev.buckets'
```

Failure modes worth testing by hand: no/garbage token → **401** (generic); a token minted for
`grype` pushing a trivy envelope → **403** (scope binding); a >10 MiB compressed body or a zip
bomb → **413**; an envelope with an extra field → **422** (`extra="forbid"`). Repeat step 4 —
counts stay stable (deterministic `_id`s → idempotent re-push).

## Inspecting OpenSearch by hand

Dev OpenSearch is `http://localhost:9200`, security off. `| jq` prettifies.

```bash
curl -s 'localhost:9200/_cat/indices/findings,system-tokens,javv-*?v'   # JAVV indices + doc counts
curl -s 'localhost:9200/findings/_mapping' | jq                         # every field + type
curl -s 'localhost:9200/_index_template/javv-scan-events' | jq          # per-cluster template
curl -s 'localhost:9200/findings/_count' | jq                           # doc count
curl -s 'localhost:9200/findings/_search?size=10' | jq '.hits.hits[]._source'   # first 10 docs

# filter: critical findings in one namespace (array-contains on namespaces[])
curl -s 'localhost:9200/findings/_search' -H 'Content-Type: application/json' -d '{
  "query": {"bool": {"filter": [
    {"term": {"severity": "critical"}},
    {"term": {"namespaces": "javv-smoke"}},
    {"term": {"present": true}}
  ]}}}' | jq '.hits.hits[]._source'

# aggregation: findings per severity (the lc normalizer folds scanner casing)
curl -s 'localhost:9200/findings/_search?size=0' -H 'Content-Type: application/json' \
  -d '{"aggs": {"by_severity": {"terms": {"field": "severity"}}}}' \
  | jq '.aggregations.by_severity.buckets'
```

Next slices: hardened `POST /api/v1/ingest/scan` (token auth, size/decompression caps,
`extra="forbid"` full-envelope model) · observability (`/metrics`, structlog `request_id`,
startup fail-fast + `/readyz` degrade) · OpenSearch service container in CI.

## Dev
```bash
cd backend
uv sync --all-extras --dev
uv run ruff check . && uv run pyright && uv run pytest
```
