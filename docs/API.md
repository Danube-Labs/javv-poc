# JAVV API reference

> Human-readable index of the backend's HTTP surface. The **live, authoritative** spec is the
> app's auto-generated OpenAPI — run the backend and open **`/docs`** (Swagger UI) or
> **`/openapi.json`**. This file is the at-a-glance map + the things OpenAPI doesn't capture (auth
> regime, capabilities, metrics, error semantics). Kept versioned in-repo (reviewed in PRs) rather
> than a wiki so it can't drift silently — **any route change updates this file in the same PR**
> (`standards/definition-of-done.md` §6). Conventions (`standards/api-design.md`): `/api/v1`
> prefix for data routes, snake_case, `extra="forbid"` request models, one problem-details error
> envelope for every non-2xx (`status`/`title`/`request_id`).

## Auth regimes (three classes)

| Regime | Mechanism | Used by |
|---|---|---|
| **none** | — | `/healthz`, `/readyz`, `/metrics` (cluster-internal; restrict by scrape topology, not app auth) |
| **machine** | `Authorization: Bearer <token>` — per-`(cluster, scanner)` 256-bit token, peppered-SHA-256 at rest, scope-bound to the payload (SEC-3) | ingest, scan-scope, scan-runs |
| **session** | httpOnly `Secure` cookie from `/auth/login`; server-side TTL + revocation; login lockout | every human endpoint |

Session endpoints marked with a **capability** additionally require it on the principal's role
bundle (D33; roles: `viewer` — none, `triager` — `can_triage`, `security_lead` — `can_triage` +
`can_accept_audit_final`, `admin` — `*`). A `must_change` session (fresh temp password, SEC-6)
can reach **only `/auth/*`** — everything else 403s until the password is changed. The
**capability column's source of truth** is `backend/tests/security/test_rbac_idor_contract.py`
(registry + exemptions); if this table and the registry disagree, the registry wins.

Tenancy: `cluster_id` is an always-applied data filter on every read/export (D38/H9), enforced in
the query layer (tenant chokepoint), not per-user grants (post-MVP).

## Endpoints

### System (M1)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/healthz` | none | Liveness — 200 while the process runs; **no OpenSearch dependency** |
| GET | `/readyz` | none | Readiness — `200 {ready}` if OpenSearch reachable, `503 {degraded}` if not |
| GET | `/metrics` | none | Prometheus exposition (see below) |

### Machine surface (M1/M3, scanner-facing)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/ingest/scan` | machine | Ingest one schema-v3 scanner envelope → findings/scan-events/images (details below) |
| GET | `/api/v1/scan-scope` | machine | The scanner reads its own cluster's scan scope; scoped to the token's `cluster_id` (D43) |
| POST | `/api/v1/scan-runs` | machine | Allocates the next `scan_order` (strictly increasing per `(cluster_id, scanner)`; CAS + forward self-heal, D45) |
| POST | `/api/v1/inventory-runs` | machine | Cycle-END inventory certification (M8a/#33): body `{scan_run_id, expected_count, started_at}` → the backend counts landed image docs server-side, allocates `inventory_order` (per-cluster D45 counter), writes the immutable manifest (`committed` iff complete; retry returns the original manifest). Token-bound to its own `cluster_id` (SEC-3) |

### Auth & sessions (M5a)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/login` | — | Session mint; generic 401 (no user-existence oracle); lockout 429 after `JAVV_LOGIN_MAX_ATTEMPTS` |
| POST | `/auth/logout` | session | Server-side revocation |
| POST | `/auth/password` | session | Password change; the only mutating route a `must_change` session may call |
| GET | `/auth/me` | session | Principal view: `username`, `role`, `capabilities`, `must_change` — **the UI gates on `capabilities`, never role names** |

### Admin (M5a)

| Method | Path | Capability | Purpose |
|---|---|---|---|
| GET/POST | `/api/v1/admin/tokens` | `can_manage_tokens` | List / mint ingest tokens (raw token returned **once**, at mint) |
| POST | `/api/v1/admin/tokens/{token_id}/revoke` | `can_manage_tokens` | Disable a token |
| POST | `/api/v1/admin/tokens/{token_id}/rotate` | `can_manage_tokens` | New secret, same scope |
| GET/POST | `/api/v1/admin/users` | `can_manage_users` | List / create users (`system`/`fleet` usernames reserved → 422) |
| PATCH | `/api/v1/admin/users/{username}/role` | `can_manage_users` | Role change (revokes the user's sessions) |
| PATCH | `/api/v1/admin/users/{username}/disabled` | `can_manage_users` | Enable/disable; the **last enabled admin** cannot be disabled (409) |
| POST | `/api/v1/admin/users/{username}/password-reset` | `can_manage_users` | Temp password + `must_change` |

### Findings — read (M6)

All session-auth, no capability (reads). All take the filter family (`cluster_id` **required**,
`scanner`, `severity`, `state`, `namespace`, `image`, `cve_id`, `kev`, `fixable`, `disagree`, …)
and the global `as_of`. **T<now dispatches to the M8b reader (live since #34)** — results are
reconstructed from the append logs as-scanned: fields history deliberately does not record
(`kev`, `epss`, `disagree`, `image_repo`, `tag`, `app`) come back `null`; a filter/sort/group on
one of them at a past T is a 422; whitelisted facets on them return empty buckets. Queued exports
(`POST /api/v1/reports`) accept a past `as_of_t` too — the drain reconstructs at T (inline export
routes stay current-state-only).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/findings` | PIT + `search_after` paged search; returns rows + an opaque `cursor` |
| GET | `/api/v1/findings/facets` | Scanner-faceted aggregations (counts per severity/state/… per scanner) |
| GET | `/api/v1/findings/groups` | Composite group paging (e.g. by CVE across images) |
| GET | `/api/v1/trends/scans` · `/api/v1/trends/findings` | Time series from scan-events; `resolved_semantics: "scan_resolved"` (A-m9 — *scan-observed* resolution, not human `state=resolved`) |
| GET | `/api/v1/contributors` | Triage-work leaderboard + TTR/SLA-hit from `system-audit-log` (FR-15) |
| GET | `/api/v1/scanners/freshness` | Per-(cluster, scanner) `last_ingest_at` + `silent_for_seconds` (FR-6/D20 banner; #218). Max across tokens; disabled tokens count; never-ingested → nulls |

**Cursor errors (A-m1):** expired PIT → **410** (re-run the search); tampered/invalid cursor →
**422**; OpenSearch transport failure → **503**. The PIT slot is released on every error path.

### Findings — triage & decisions (M5b/M5c/M5d)

| Method | Path | Capability | Purpose |
|---|---|---|---|
| PATCH | `/api/v1/findings/{finding_key}/triage` | `can_triage` | One VEX-model transition (`state` ∈ open/acknowledged/not_affected/risk_accepted/resolved; `vex_justification` required iff `not_affected`); CAS'd on the doc; journaled (D17) |
| POST | `/api/v1/findings/bulk-triage` | `can_triage` | **Bounded-synchronous** (A-Mc): frozen selector set ≤ `JAVV_BULK_INLINE_LIMIT` (5000) applies now; above → **413**; selector materializing > `JAVV_BULK_MAX_TARGETS` (10000) → **413** "selector too broad". Empty selector → 422. One journal row per action |
| POST/GET | `/api/v1/decisions` | `can_triage` | Create / list decisions (ignore-rules etc.). **Immutable + lifecycle stamp** — edit = revoke+new. `risk_accepted` type additionally requires `can_accept_audit_final` (SEC-2 → 403 without it) |
| PATCH | `/api/v1/decisions/{decision_id}` | `can_triage` | The revoke+new edit (one `effective_at`/`operation_id`, D40) |
| POST | `/api/v1/decisions/{decision_id}/revoke` | `can_triage` | Revoke (projection un-applies) |
| GET | `/api/v1/decisions/approvals` | `can_accept_audit_final` | The approvals queue (security-lead view) |

### Settings (M5d)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/settings/sla` | session | Read SLA policy (crit/high/med/low/KEV days) |
| PUT | `/api/v1/settings/sla` | `can_manage_settings` | Replace SLA policy |

### Exports (M6) & scheduled reports (M7)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/findings/export.csv` | session | Streaming, **CSV-injection-sanitized** export of any lens. > `JAVV_EXPORT_MAX_ROWS` (50k) → **413** (narrow the lens or schedule) |
| GET | `/api/v1/findings/export.vex` | session | OpenVEX/CycloneDX per **one scanner** (`scanner` required — per-scanner is sacred); same row cap |
| POST | `/api/v1/reports` | session · `kind: bulk_triage` → `can_triage` | Enqueue a scheduled job. `kind: export` is session-only *by design* (a scheduled export is a read). `kind: bulk_triage` is gated like the inline bulk (`can_triage`; + `can_accept_audit_final` for risk-accepts) — the selector **freezes to `target_ids` at enqueue**, and the inline 5000 ceiling is lifted (only the 10k freeze cap applies → **413**) |
| GET | `/api/v1/reports/{report_id}` | session | Job status (public view — never leaks `params`/`attempt_id`/lease fields). 404 unknown. For a `done`, unexpired report also mints the short-lived (15 min) signed `download_token` — refetch for a fresh one |
| GET | `/api/v1/reports/{report_id}/download` | session + `token` | Streams the result chunks in order (CSV or VEX JSON). **410** past `expires_at` (re-run the export) · 404 no result yet · 403 bad/stale token |
| GET | `/api/v1/notifications` | session | The bell (FR-16, polled — no broker): own notifications only, newest 50, + server-computed `unread` count |
| PATCH | `/api/v1/notifications/{notification_id}/read` | session | Mark one of **your own** read — anyone else's id is 404 (IDOR-indistinguishable from missing) |

Exports + search cursors share a **per-principal concurrent-PIT cap**
(`JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL`, 10) → **429 + `Retry-After`** past it. Scheduled-report
results are stored in OpenSearch chunks with `expires_at` (default 24 h); the drain worker
(`python -m backend.jobs.report_drain`, k8s CronJob in M10) claims jobs via OCC + fencing
`attempt_id`, throttles with `JAVV_REPORT_DRAIN_SLEEP_MS`, fails jobs past `JAVV_EXPORT_MAX_BYTES`,
and rings a `report_ready` bell on completion.

### POST `/api/v1/ingest/scan` (the hardened surface)

Request: a **schema-v3 scanner envelope** (v3 = the D44 `effective_config` stamp; **current-only**
— older schema versions 422, scanner + backend deploy in lockstep), JSON, optionally
`Content-Encoding: gzip`.

Defenses, in order: per-token rate limit → bearer auth → compressed-size cap (streamed) →
decompression cap (zip-bomb) → JSON parse → full-envelope `extra="forbid"` validation →
token↔payload scope binding → commit-then-cache writes (D39, deterministic `_id`s → idempotent).

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
| `javv_http_request_duration_seconds` | histogram | `method`, `route`, `status` | Route-TEMPLATE labels (unrouted → one `unmatched` series); `/metrics` + probes excluded (#220 M-1) |
| `javv_opensearch_request_errors_total` | counter | `kind` | `conn`, `timeout`, `429`, `503` — dependency failures on read + bulk paths (M-2) |
| `javv_opensearch_backoff_retries_total` | counter | — | Per-item 429/503 bulk retries — the saturation signal (the only flow control without a broker) |
| `javv_cas_conflicts_total` | counter | `site` | `watermarks`, `scan_orders`, `reproject` (+ `report_claim`, M7 slice 2) — multi-writer contention early warning (M-3) |
| `javv_limit_rejections_total` | counter | `limit` | `pit_cap`, `export_rows`, `bulk_targets`, `bulk_inline` (M-4) |
| `javv_pits_open` | gauge | — | Open PIT slots (per pod, like the guard) |
| `javv_export_rows_total` / `javv_export_bytes_total` | counter | `format` | What was **actually** streamed (a disconnected client counts what it got) |
| `javv_auth_failures_total` | counter | `reason` | `bad_credentials`, `locked_out`, `expired_session`, `missing_capability` — never a username label (M-5) |

Plus the default `prometheus_client` process/GC gauges. The scrape is **storage-free** (no
OpenSearch call) — it keeps working during an outage, exactly when it's needed. Single-process
registry (one uvicorn worker); multi-worker needs the multiprocess mode (noted in
`core/metrics.py` for M10). SLO/alerting rules on top are **owned by M10**
(`prometheus-rules.yaml`).

## Logging

Structured JSON via the **shared `libs/javv-common` structlog pipeline only** (observability.md
§1). Every request binds a `request_id` (from `X-Request-ID` if well-formed — `[A-Za-z0-9-]{1,64}`
— else minted; echoed in the response header); ingest also binds `cluster_id`/`scanner`. The
redaction processor masks token/secret/password/authorization/pepper/session/cookie keys and
scrubs `Bearer …` substrings from every event — tokens never reach a log line (tested at both
layers). OpenSearch client request/response **bodies never log at any level**.

## Auth model (MVP) — summary

- **Machine:** per-`(cluster, scanner)` bearer tokens (`system-tokens`), peppered-SHA-256 at
  rest, scope-bound, mint/revoke/rotate via the admin API (or `python -m backend.core.tokens`).
- **Human:** local users (argon2id), server-side sessions, capability-based RBAC (D33), bootstrap
  admin seeded from env/secret with forced first-login rotation (SEC-6), login lockout, no
  user-existence oracles.
- **Tenancy:** `cluster_id` always-applied data filter (per-user cluster grants post-MVP).
