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
| POST | `/api/v1/ingest/scan` | machine | Ingest one scanner envelope (schema **v3 or v4** — the M8d ptype rollout window; v3 findings get `ptype: null`) → findings/scan-events/images (details below) |
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
| GET | `/api/v1/admin/roles` | `can_manage_users` | The seeded `system-roles` capability bundles (A-4 — the UI renders whatever is seeded; M9e) |
| GET | `/api/v1/admin/snapshots` | `can_manage_retention` | The configured repo's snapshots, newest first (`configured: false` empty state until a repo ref exists; M9e) |
| POST | `/api/v1/admin/snapshots` | `can_manage_retention` | Manual snapshot of the durability set (202 fire-and-forget; 409 without a repo). Journaled (D17) |
| POST | `/api/v1/admin/snapshots/{snapshot_name}/restore` | `can_restore_snapshot` | Restore into `restored-*` copies — **never onto live indices**; promoting a copy is a manual step. Journaled (D17) |
| GET | `/api/v1/admin/opensearch-runtime` | `can_manage_settings` | Allowlist-shaped runtime facts (version, health, nodes/roles/heap, `discovery.type`, `path.repo`, security state) — the §D read-only card; never a raw passthrough |

### Findings — read (M6)

All session-auth, no capability (reads). All take the filter family (`cluster_id` **required**,
`scanner`, `severity`, `state`, `namespace`, `image`, `cve_id`, `kev`, `fixable`, `disagree`,
`ptype`, …) and the global `as_of`. `severity` values are the **full-word canonical vocabulary**
(D46/#274: `critical|high|medium|low|negligible|unknown`) served by the server-derived
`severity_canonical` key — facet bucket keys are the same words; the verbatim scanner word stays
display-only in rows. `ptype` (M8d/#241) is also a facet (pre-v4 rows bucket as
`"unknown"` until a sweep heals them, D30) and a group dim — and unlike `kev`/`epss` it IS
recorded on occurrences, so it stays filterable/facetable at a past `as_of` (v3-era rows are
honestly `null` there). `overdue=true|false` (issue #363) filters on the **materialized D21 group
clock** (`sla_clock_at`) against cutoffs derived from the **live SLA policy at query time** — a
policy edit moves the filter instantly, chip ≡ filter by construction (shared handled-states set,
KEV fast-lane included); works on grid/facets/groups/exports, and at a past `as_of` it filters the
reconstruction's own read-time verdict (judged at `now=T`, never the cache field). Multi-page grid
walks freeze the cutoffs in the cursor (the PIT freezes docs, the query freezes with them).
**T<now dispatches to the M8b reader (live since #34)** — results are
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
| GET | `/api/v1/trends/scans` · `/api/v1/trends/findings` | Time series from scan-events; `resolved_semantics: "scan_resolved"` (A-m9 — *scan-observed* resolution, not human `state=resolved`). `/findings` also takes `split=scanner\|severity` (severity = the D16 server-derived canonical, six buckets; **now-only** — 422 at a past `as_of`) and an optional `scanner=trivy\|grype` query-filter scope (M9c 1b) |
| GET | `/api/v1/contributors` | Triage-work leaderboard + TTR/SLA-hit from `system-audit-log` (FR-15). `totals` (M9d slice 3) = the team KPI block: exact team-wide `by_action` (top-level agg, never board-capped), **pooled** median TTR / SLA-hit (never median-of-medians), `critical_cleared`; same block at a rewound `as_of` |
| GET | `/api/v1/scanners/freshness` | Per-(cluster, scanner) `last_ingest_at` + `silent_for_seconds` (FR-6/D20 banner; #218). Max across tokens; disabled tokens count; never-ingested → nulls |
| GET | `/api/v1/scanners/provenance` | Per-(cluster, scanner) versions/`effective_config` of the latest **committed** run + last-N runs (`?runs=`, ≤50). Catalog-first (R-CATALOG); latest = max `scan_order`, never `@timestamp` (M8c/#240) |
| GET | `/api/v1/audit` | The journaled history, plain-session read (M8c/#240): filters `entity_type`/`action`/`actor`, ordered `(@timestamp, event_id)` (`?order=`, desc default), same opaque-cursor paging + A-m1 semantics as `/findings`. `as_of` (M9d/D28) bounds the walk at a rewound T — absent/`now` = unbounded. Rows are **decorated at read** (M9d): `finding`/`decision` sub-objects carry the touched entity's identity (cve/image/scanner/type), `null` once the doc ages out — history stays untouched, decoration is display-only and tenant-checked per doc (SEC-4) |
| GET | `/api/v1/audit/facets` | Rail counts for the audit screen (M9d): `entity_type`/`action`/`actor` terms aggs under the same filters + `as_of` bound as the walk. `interval=day\|hour` + `window_days` adds `activity` — the audit lens's events-over-time histogram (quiet buckets as zeros) |
| GET | `/api/v1/audit/export.csv` | Streaming CSV of the audit lens (M9d): decorated + CSV-injection-sanitized, constant-memory PIT sweep; > `JAVV_EXPORT_MAX_ROWS` → **413**, PIT cap → **429** (same bounds as the findings export) |
| GET | `/api/v1/images` | Running images = the latest **committed** inventory run's image docs (M8c/#240; the T=now case of M8b's `running_images_at` — shared primitives). Partial runs never leak; clean (zero-finding) images appear; `inventory: null` = no committed inventory yet (unknown ≠ empty) |
| GET | `/api/v1/images/timeline` | One `repo:tag`'s committed scan-event history (`cluster_id` + `image_repo` + `tag` query params) for the image-detail digest sub-timeline — build-change (digest flips) and per-scanner gap markers derive client-side |
| GET | `/api/v1/clusters` | Cluster listing (D-5): token-derived `cluster_id`s ∪ registry names; `cluster_name` defaults to the id. **Display-only** — never a query key |

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
| GET | `/api/v1/decisions/approvals` | `can_accept_audit_final` | The approvals queue (security-lead view): ACTIVE risk-accepts, soonest expiry first, `size`/`offset` paging. Slice 4b filters, all server-side: `q` (CVE contains) · `status` (`active\|expiring\|expired\|open-ended`, derived from `expiry` at query time against `warn_days`, default 7 — mirrors the UI chip) · `created_by` · `scanner` (`both\|trivy\|grype`, the column value). Response carries `facets` (status/created_by/scanner counts under the same lens) |

### Settings (M5d)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/settings/sla` | session | Read SLA policy (`critical_days`/`high_days`/`medium_days`/`low_days`/`kev_days` — full-word knobs, D46/#274) |
| PUT | `/api/v1/settings/sla` | `can_manage_settings` | Replace SLA policy |
| GET | `/api/v1/settings/staleness` | session | Effective D20 timers for `?cluster_id` (its override if set, else the fleet default) + `per_cluster_override` (M9e) |
| PUT | `/api/v1/settings/staleness` | `can_manage_settings` | Replace the timers; `cluster_id` in the body writes the per-cluster override, absent = the fleet default. Journaled (D17) |
| GET | `/api/v1/settings/scan-scope` | session | The D-2 session read of `?cluster_id`'s scan scope (the bearer `GET /api/v1/scan-scope` stays scanner-only; M9e) |
| PUT | `/api/v1/scan-scope` | `can_manage_settings` | Replace a cluster's scan scope (D43/FR-24: empty include = all, ignore wins). Journaled (D17) |
| GET | `/api/v1/settings/data` | `can_manage_retention` | The Data & OpenSearch panel's one read: effective lifecycle knobs for `?cluster_id` (+ `per_cluster_override`), report TTL, findings-cleanup window, snapshot repo ref (M9e) |
| PUT | `/api/v1/settings/retention` | `can_manage_retention` | Set `retention_days` (RMW of the lifecycle doc; `cluster_id` in body = the per-cluster override). Journaled (D17) |
| PUT | `/api/v1/settings/rollover` | `can_manage_retention` | Set `max_age_days`/`max_docs`/`max_size_gb` (same doc/override rule). Journaled (D17) |
| PUT | `/api/v1/settings/report-ttl` | `can_manage_retention` | Set the export TTL `hours` (fleet-wide `report_ttl` knob — the row-11 graduation of `JAVV_EXPORT_TTL_HOURS`). Journaled (D17) |
| PUT | `/api/v1/settings/findings-cleanup` | `can_manage_retention` | Set the D37/M12 long `cleanup_days` window (fleet-wide; consumed by the findings-cleanup job). Journaled (D17) |
| PUT | `/api/v1/clusters/{cluster_id}/name` | `can_manage_settings` | Rename a cluster's display name (M8c/#240): journaled per D17 (journal-first), stored in the `system-config` `cluster-registry` doc via a seq_no-CAS write. `cluster_id` itself is immutable |

### Saved views (M8e, C-6)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/views` | session | List saved views — visible to **all** authenticated users (C-6; per-view ACLs post-MVP). Card counts come from `/findings/facets` at render time, never stored |
| POST | `/api/v1/views` | session | Save a view (`owner` = principal, immutable). `preset` mirrors the findings filter family 1:1 and is validated against the **closed vocabularies** (lowercase canonical severities incl. `negligible`, the 6 states, scanner, ptype shape) — garbage → 422, never stored. Journaled (D17, journal-first) |
| PATCH | `/api/v1/views/{view_id}` | session, **owner-or-admin** | Edit name/description/preset (partial; preset replaces whole). Non-owner without `can_manage_settings` → 403 (the IDOR case); `owner` is unrepresentable in the body. seq_no-CAS write → **409** on a concurrent edit. Journaled |
| DELETE | `/api/v1/views/{view_id}` | session, **owner-or-admin** | Delete (204). Journal row carries the frozen doc, so deleted views stay auditable |

### Exports (M6) & scheduled reports (M7)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/findings/export.csv` | session | Streaming, **CSV-injection-sanitized** export of any lens. > `JAVV_EXPORT_MAX_ROWS` (50k) → **413** (narrow the lens or schedule) |
| GET | `/api/v1/findings/export.vex` | session | OpenVEX/CycloneDX per **one scanner** (`scanner` required — per-scanner is sacred); same row cap |
| POST | `/api/v1/reports` | session · `kind: bulk_triage` → `can_triage` | Enqueue a scheduled job. `kind: export` is session-only *by design* (a scheduled export is a read). `kind: bulk_triage` is gated like the inline bulk (`can_triage`; + `can_accept_audit_final` for risk-accepts) — the selector **freezes to `target_ids` at enqueue**, and the inline 5000 ceiling is lifted (only the 10k freeze cap applies → **413**) |
| GET | `/api/v1/reports/{report_id}` | session (owner) | Job status (public view — never leaks `params`/`attempt_id`/lease fields). 404 unknown **or not yours** (a foreign `report_id` is indistinguishable from missing). For a `done`, unexpired report also mints the short-lived (15 min) signed `download_token` — refetch for a fresh one |
| GET | `/api/v1/reports/{report_id}/download` | session (owner) + `token` | Streams the result chunks in order (CSV or VEX JSON). **410** past `expires_at` (re-run the export) · 404 no result yet · 403 bad/stale token |
| GET | `/api/v1/notifications` | session | The bell (FR-16, polled — no broker): own notifications only, newest 50, + server-computed `unread` count |
| PATCH | `/api/v1/notifications/{notification_id}/read` | session | Mark one of **your own** read — anyone else's id is 404 (IDOR-indistinguishable from missing) |

Exports + search cursors share a **per-principal concurrent-PIT cap**
(`JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL`, 10) → **429 + `Retry-After`** past it. Scheduled-report
results are stored in OpenSearch chunks with `expires_at` (default 24 h); the drain worker
(`python -m backend.jobs.report_drain`, k8s CronJob in M10) claims jobs via OCC + fencing
`attempt_id`, throttles with `JAVV_REPORT_DRAIN_SLEEP_MS`, fails jobs past `JAVV_EXPORT_MAX_BYTES`,
and rings a `report_ready` bell on completion.

### POST `/api/v1/ingest/scan` (the hardened surface)

Request: a **scanner envelope, schema v3 or v4** (the M8d ptype rollout window — anything
outside it 422s; v3 = the D44 `effective_config` stamp), JSON, optionally
`Content-Encoding: gzip`. **Third-party pushers:** the full public contract — JSON Schema,
call protocol, worked example — is [`INGEST-CONTRACT.md`](INGEST-CONTRACT.md) (#327).

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
| `422` | Envelope failed validation (extra field, bad `cluster_id` shape, counts invariant, `schema_version` outside the accepted window — v3/v4 during the M8d rollout) |
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
