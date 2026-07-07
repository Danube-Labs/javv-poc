# 02 — `/metrics`: do we expose useful stuff?

## Verdict: ⚠️ ingest-only — fine for M1, thin for what the app is now

`backend/core/metrics.py` (verified): exactly three counters —
`javv_ingest_accepted_total{scanner}`, `javv_ingest_rejected_total{reason}`,
`javv_ingest_findings_written_total{scanner}` — plus the `prometheus_client` default process/GC
collectors. Endpoint is unauthenticated, no OpenSearch dependency (deliberate, like `/healthz`).

Since M1 the app grew a read/query surface, human auth, decisions/bulk-triage, exports, and the
M7 queue — **none of it is observable**. An operator today cannot answer: is search slow? are
sessions failing? did an export get killed by the row cap? are CAS retries churning? SLO/alerting
rules are owned by M10 (`prometheus-rules.yaml`) — M10 has nothing to alert *on* beyond ingest.

## Expansion guide (one `feat` PR)

All additions go in `core/metrics.py` (one module, one registry — the existing pattern). Naming:
`javv_<area>_<thing>_<unit-or-total>`. Every new metric lands in the API.md metrics table
**in the same PR** (that table is the metrics contract, per 04).

**M-1 — HTTP request histogram (the workhorse).** Starlette middleware in `main.py` (register
next to the request-id middleware):

```
javv_http_request_duration_seconds{method, route, status}  # histogram
```

Edge cases — these decide whether the metric is usable or a cardinality bomb:
- **Label by route TEMPLATE, never raw path** (`/api/v1/findings/{finding_key}/triage`, not the
  concrete key). Obtain it from `request.scope["route"].path` *after* routing; requests that match
  no route (404s on garbage paths) get `route="unmatched"` — do not use the raw path there either,
  or an attacker mints unbounded series by scanning paths.
- Exclude `/metrics` itself and `/healthz`/`/readyz` probes (they dominate volume and skew p99),
  or label them and let the M10 rules filter — pick **exclude**, simpler.
- `status` = the 3-digit class as-is (`"200"`, `"413"`); on unhandled exception record `"500"`
  **before** re-raising (wrap in `try/finally` with a status captured from the response or the
  exception path).
- Default buckets are wrong for a search API — use
  `(0.005, 0.025, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)` (30 s = the OS client timeout).

**M-2 — OpenSearch dependency health.**
- `javv_opensearch_request_errors_total{kind}` — increment in the shared bulk-backoff helper and
  the read paths' exception handlers; `kind ∈ {conn, timeout, 429, 5xx}` (bounded set, map
  everything else to `other`).
- `javv_opensearch_backoff_retries_total` — the 429/503 backoff helper is the only flow control
  we have; its retry rate IS the saturation signal.

**M-3 — concurrency-control churn.** `javv_cas_conflicts_total{site}` with
`site ∈ {watermarks, reconcile, scan_orders, reproject, report_claim}` (add `report_claim` when M7
slice 2 lands — coordinate: if slice 2 is already merged when implementing, wire it in the same
PR). A rising conflict rate is the early warning for the multi-writer races the D40 design guards.

**M-4 — read/limit pressure.** Counters, incremented where the 4xx is raised:
- `javv_limit_rejections_total{limit}` — `limit ∈ {pit_cap, export_rows, bulk_targets, bulk_inline,
  rate_limit, lockout}`. One counter, one label — do not mint six counters.
- `javv_pits_open` gauge — set from `pit_guard`'s live-slot count on acquire/release (module
  already owns the state; expose `def open_slots() -> int`).
- `javv_export_rows_total{format}` / `javv_export_bytes_total{format}` — increment at stream end
  (CSV) and document end (VEX). Edge case: a client that disconnects mid-stream — increment what
  was actually written (the `_guarded()` generator's `finally` already runs; count there).

**M-5 — auth signals.** `javv_auth_failures_total{reason}` with
`reason ∈ {bad_credentials, locked_out, disabled, expired_session, missing_capability}`.
**Never a username label** (unbounded + PII in the exposition). `javv_sessions_active` is NOT
worth it (requires an OS query at scrape time — violates the "no OpenSearch dependency" property
of the endpoint; skip).

**M-6 — M7 queue (when slice 3+ lands).** `javv_reports_enqueued_total{kind}`,
`javv_reports_completed_total{kind, outcome}` (`outcome ∈ {done, failed, expired_lease}`).
Queue-depth gauge: **do not** query OpenSearch at scrape; the drain job logs depth per pass and
M10 can alert on staleness instead. Keep `/metrics` storage-free — that property is what makes it
safe to scrape during an OpenSearch outage (exactly when you need it).

**Auth on /metrics:** keep none (cluster-internal). Note for M10's README: restrict via
NetworkPolicy/scrape-config, not app auth — Prometheus-with-credentials is M10 scope creep.

**Multiprocess caveat:** we run single-process uvicorn; if M10 ever moves to multiple workers,
`prometheus_client` needs its multiprocess mode (env dir + registry swap). Leave a one-line
comment on the registry in `core/metrics.py` so the M10 implementer trips over it.

## Tests (TDD — extend `tests/test_observability.py`)
- request histogram: hit `/api/v1/findings` (401 is fine — still a routed request), assert the
  series appears with `route="/api/v1/findings"` and never a raw-path label; hit a garbage path,
  assert `unmatched`.
- limit counter: trip the PIT cap (existing `test_pit_guard` fixtures make this cheap), assert
  `javv_limit_rejections_total{limit="pit_cap"}` increments.
- the M-1 exclusion: scrape `/metrics` twice, assert no `route="/metrics"` series.

## Where to record
- API.md metrics table (04's rewrite adds it; if this PR lands first, edit the current table).
- M10 bolt README (`## Updates`): "prometheus-rules.yaml scope: rules for the M-1..M-6 series;
  /metrics stays unauthenticated, restrict by scrape topology" + mirror to issue #41.
