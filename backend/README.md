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

Next slices: hardened `POST /api/v1/ingest/scan` (token auth, size/decompression caps,
`extra="forbid"` full-envelope model) · observability (`/metrics`, structlog `request_id`,
startup fail-fast + `/readyz` degrade) · OpenSearch service container in CI.

## Dev
```bash
cd backend
uv sync --all-extras --dev
uv run ruff check . && uv run pyright && uv run pytest
```
