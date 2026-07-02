# JAVV API reference

> Human-readable index of the backend's HTTP surface. The **live, authoritative** spec is the
> app's auto-generated OpenAPI — run the backend and open **`/docs`** (Swagger UI) or
> **`/openapi.json`**. This file is the at-a-glance map + the things OpenAPI doesn't capture (auth,
> caps, metrics). Kept versioned in-repo (reviewed in PRs) rather than a wiki so it can't drift
> silently. Conventions (`standards/api-design.md`): `/api/v1` prefix for data routes, snake_case,
> `extra="forbid"` request models, one problem-details error envelope for every non-2xx.

## Endpoints

| Method | Path | Auth | Purpose | Bolt |
|---|---|---|---|---|
| GET | `/healthz` | none | Liveness — 200 as long as the process runs; **no OpenSearch dependency** | M1 |
| GET | `/readyz` | none | Readiness — `200 {ready}` if OpenSearch reachable, `503 {degraded}` if not | M1 |
| GET | `/metrics` | none | Prometheus exposition (see below) | M1 |
| POST | `/api/v1/ingest/scan` | **Bearer token** | Ingest one scanner envelope → findings/scan-events/images | M1 |
| GET | `/api/v1/scan-scope` | **Bearer token** | The scanner reads its own cluster's scan scope (namespaces/images/kinds to scan); scoped to the token's `cluster_id` (D43) | #94 |

Everything below `/api/v1` is added by later bolts (read/query APIs M6/M8b, auth M5a, decisions
M5c, exports M7, …) — they'll be listed here as they land.

### POST `/api/v1/ingest/scan`
The hardened, untrusted-input surface. Request: a **schema-v3 scanner envelope** (v3 = the D44
`effective_config` stamp; **current-only** — older schema versions 422, scanner + backend deploy in
lockstep), JSON, optionally
`Content-Encoding: gzip`. Auth: `Authorization: Bearer <token>` (256-bit; minted via
`python -m backend.core.tokens`; stored only as a peppered SHA-256).

Defenses, in order: per-token rate limit → bearer auth → compressed-size cap (streamed) →
decompression cap (zip-bomb) → JSON parse → full-envelope `extra="forbid"` validation →
token↔payload scope binding → commit-then-cache writes (D39, deterministic `_id`s → idempotent).

Responses:

| Code | When |
|---|---|
| `202` | Accepted — `{accepted, findings, commit}` |
| `400` | Body not valid JSON / not valid gzip |
| `401` | Missing/invalid/disabled token (generic — no existence oracle) |
| `403` | Token scope ≠ payload `cluster_id`/`scanner` (SEC-3) |
| `413` | Compressed body > cap, or decompressed > cap (zip bomb) |
| `422` | Envelope failed validation (extra field, bad `cluster_id` shape, counts invariant, non-current `schema_version`) |
| `429` | Per-token rate limit exceeded |
| `503` | Storage temporarily unavailable (bulk retries exhausted) |

## Metrics (`/metrics`, Prometheus)

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `javv_ingest_accepted_total` | counter | `scanner` | Envelopes accepted + committed |
| `javv_ingest_rejected_total` | counter | `reason` | Envelopes rejected — `reason` ∈ `bad_token`, `rate_limited`, `too_large`, `bad_gzip`, `bad_json`, `invalid_envelope`, `scope_mismatch`, `storage_error` |
| `javv_ingest_findings_written_total` | counter | `scanner` | Finding docs written |

Plus the default `prometheus_client` process/GC gauges. SLO/alerting rules on top of these are a
later ops concern (no bolt owns it yet — audit gap).

## Logging

Structured JSON (structlog). Every request binds a `request_id` (from `X-Request-ID` or minted,
echoed back in the response header); ingest also binds `cluster_id`/`scanner`. A **redaction
processor** masks token/secret/password/authorization/pepper keys and scrubs `Bearer …` substrings
from every event — tokens never reach a log line (tested).

## Auth model (MVP)

- **Ingest:** per-`(cluster, scanner)` bearer tokens (`system-tokens`), peppered-SHA-256 at rest,
  scope-bound to the payload. Mint: `python -m backend.core.tokens --cluster <id> --scanner trivy`.
- **Human endpoints / RBAC:** not yet — capability-based auth + sessions land in **M5a** (#27).
- **Tenancy:** `cluster_id` is a data filter applied on every read/agg (D38/H9), not yet a per-user
  boundary.
