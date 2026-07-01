# JAVV backend

FastAPI (async) + `AsyncOpenSearch`. Ingests the M0 scanner envelope and serves the read/reporting
API — every number comes from an OpenSearch aggregation (server-side; no raw findings to the client).
Bolt: **M1** (`development/bolts/M1-backend-skeleton/`, #23).

## Layout (STACK-BEST-PRACTICES §1)
```
src/backend/
  core/       settings · lifespan (single AsyncOpenSearch client) · errors (problem-details envelope)
  routers/    HTTP layer — health now; ingest + read APIs next
  main.py     app factory (create_app)
```
Next slices: versioned index bootstrap (`dynamic:false` mappings) · hardened `POST /api/v1/ingest/scan`
(token auth, size/decompression caps, `extra="forbid"` full-envelope model) · observability
(`/metrics`, structlog `request_id`, startup fail-fast + `/readyz` degrade).

## Dev
```bash
cd backend
uv sync --all-extras --dev
uv run ruff check . && uv run pyright && uv run pytest
```
