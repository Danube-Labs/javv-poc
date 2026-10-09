# JAVV API reference

> Human-readable index of the backend's HTTP surface. The **live, authoritative** spec is the
> app's auto-generated OpenAPI — run the backend and open **`/docs`** (Swagger UI) or
> **`/openapi.json`**. This file is the at-a-glance map + the things OpenAPI doesn't capture (auth
> regime, capabilities, metrics, error semantics). Kept versioned in-repo (reviewed in PRs) rather
> than a wiki so it can't drift silently — **any route change updates this file in the same PR**
> (`standards/definition-of-done.md` §6). Conventions (`standards/api-design.md`): `/api/v1`
> prefix for data routes, snake_case, `extra="forbid"` request models, one problem-details error
> envelope for every non-2xx (`status`/`title`/`request_id`). **List responses come in three
> envelope shapes**, picked by pagination style (cursor → `data` + `next_cursor`; offset → a named
> key + a bare `total`; unpaged → a named key alone) — the shapes, the two routes that break the
> pattern, and how to read one without silently getting `0` are in
> [`standards/api-design.md`](https://github.com/Danube-Labs/javv-poc/blob/main/development/standards/api-design.md) § *List response envelopes*.

## Auth regimes (three classes)

| Regime | Mechanism | Used by |
|---|---|---|
| **none** | — | `/healthz`, `/readyz`, `/metrics` (cluster-internal; restrict by scrape topology, not app auth) |
| **machine** | `Authorization: Bearer <token>` — per-`(cluster, scanner)` 256-bit token, peppered-SHA-256 at rest, scope-bound to the payload (SEC-3) | ingest, scan-scope, scan-runs |
| **session** | httpOnly cookie from `/auth/login`, `Secure` unless `JAVV_SESSION_COOKIE_SECURE=false`; server-side TTL + revocation; login lockout | every human endpoint |

Session endpoints marked with a **capability** additionally require it on the principal's role
bundle (D33; roles: `viewer` — none, `triager` — `can_triage`, `security_lead` — `can_triage` +
`can_accept_audit_final`, `admin` — `*`). A `must_change` session (fresh temp password, SEC-6)
can reach **only `/auth/*`** — everything else 403s until the password is changed. The
**capability column's source of truth** is `backend/tests/security/test_rbac_idor_contract.py`
(registry + exemptions); if this table and the registry disagree, the registry wins.

Tenancy: `cluster_id` is an always-applied data filter on every read/export (D38/H9), enforced in
the query layer (tenant read path), not per-user grants (post-MVP).

## Endpoints

### System (M1)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/healthz` | none | Liveness — 200 while the process runs; **no OpenSearch dependency** |
| GET | `/readyz` | none | Readiness — `200 {ready}` if OpenSearch reachable, `503 {degraded}` if not |
| GET | `/metrics` | none | Prometheus exposition (see below) |
| GET | `/api/v1/meta` | session | What this backend runs: `{version, mapping_version, envelope_versions, opensearch_version, python_version}` (issues 261, 341). `version` is the release (`backend/src/backend/version.py`, bumped by release-please); `mapping_version` is `MAPPING_VERSION`; `envelope_versions` are the ingest `schema_version`s accepted; `opensearch_version` is read live from the store per request, and is `null` when the store is unreachable (the rest still answers; the miss is logged as `opensearch version unavailable` and counted in `javv_opensearch_request_errors_total{kind}`); `python_version` is the backend's interpreter. Behind login because `/readyz` is anonymous; the `bootstrap complete` log line carries the release and mapping versions for operators |

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
| GET/POST | `/api/v1/admin/tokens` | `can_manage_tokens` | List / mint ingest tokens (raw token returned **once**, at mint). List pages with `size` (≤1000, default 100) / `offset` (≤9000); optional `cluster_id` |
| POST | `/api/v1/admin/tokens/{token_id}/revoke` | `can_manage_tokens` | Disable a token |
| POST | `/api/v1/admin/tokens/{token_id}/rotate` | `can_manage_tokens` | New secret, same scope |
| GET/POST | `/api/v1/admin/users` | `can_manage_users` | List / create users (`system`/`fleet` usernames reserved → 422). List pages with `size` (≤1000, default 100) / `offset` (≤9000) |
| PATCH | `/api/v1/admin/users/{username}/role` | `can_manage_users` | Role change (revokes the user's sessions) |
| PATCH | `/api/v1/admin/users/{username}/disabled` | `can_manage_users` | Enable/disable; the **last enabled admin** cannot be disabled (409) |
| POST | `/api/v1/admin/users/{username}/password-reset` | `can_manage_users` | Temp password + `must_change` |
| GET | `/api/v1/admin/roles` | `can_manage_users` | The seeded `system-roles` capability bundles (A-4 — the UI renders whatever is seeded; M9e) |
| GET | `/api/v1/admin/snapshots` | `can_manage_retention` | The configured repo's snapshots, newest first (`configured: false` empty state until a repo ref exists; M9e) |
| POST | `/api/v1/admin/snapshots` | `can_manage_retention` | Manual snapshot of the durability set (202 fire-and-forget; 409 without a repo). Journaled (D17) |
| POST | `/api/v1/admin/snapshots/{snapshot_name}/restore` | `can_restore_snapshot` | Restore into `restored-*` copies — **never onto live indices**; promoting a copy is a manual step. Journaled (D17) |
| GET | `/api/v1/admin/opensearch-runtime` | `can_manage_settings` | Allowlist-shaped runtime facts (version, health, nodes/roles/heap, `discovery.type`, `path.repo`, security state) — the §D read-only card; never a raw passthrough |
| POST | `/api/v1/admin/opensearch/inspect` | `can_inspect_store` | Data inspector (issue 406): `{method, path, body}` validated against a **hard allowlist** — GET/POST on `<index>/_search`·`_count`, GET `_mapping`, and the global reads (`_cat/indices`, `_cat/shards`, `_cluster/health`, `_nodes/stats`). Credential indices (`system-users`/`-sessions`/`-tokens`) and script/PIT/scroll body keys are **422** with the reason verbatim; `size` over `JAVV_INSPECT_MAX_HITS` → 422; response over `JAVV_INSPECT_MAX_RESPONSE_BYTES` → **413**. Envelope `{took_ms, bytes, cap_bytes, body}`. Journal-first (D17): every query appends `store_inspect` (actor · method+path · query hash) |
| GET | `/api/v1/admin/jobs` | `can_inspect_store` | The status of every background job (issues 406, 556; the Data inspector's capability since issue 706, as the list carries failure text and who started each run): `{jobs, scheduler}`. One entry per kind in `jobs/registry.py` (eight), each the kind's `system-jobs` record (`status`, `requested_by`, `started_at`, `finished_at`, last `result` counts, `error`; `status: idle` when it has never run) plus `stale` (`true` when a running record's heartbeat outlived the lease TTL), `runnable` (it can be started with the route below) and its `capability` (null when not runnable), `schedule` (its cron expression from `JAVV_JOB_<KIND>_CRON`, null when it has none), `next_run_at` (UTC; null when the kind or the scheduler is switched off) and `health`. `health` is checked in this order: `failed` (the last run failed), `off` (no schedule, or the scheduler is switched off), `never_ran` (scheduled, no run on record), `overdue` (it missed a whole scheduled run: two scheduled times have passed since it last started), else `ok`. `scheduler` is `{enabled, timezone}`: whether this backend runs the schedules, and the timezone the cron expressions are read in |
| POST | `/api/v1/admin/jobs/{kind}/run` | per kind | Trigger a sanctioned maintenance job → **202** `{attempt_id}`; a fresh running lease → **409**. Kinds/capabilities: `rebuild_state` → `can_rebuild_state`, `staleness_sweep` → `can_manage_settings`, `lifecycle_sweep` → `can_drop_index` (D33 destructive tier). The five scheduled-only kinds (`runnable: false` in the list above) and unknown kinds → **404**. Exactly-once via seq_no-CAS claim + fencing `attempt_id`, shared with the backend's own scheduler (issues 459, 691 — a scheduled run skips while the card's run holds the lease, and vice versa); journaled (D17). `?dry_run=true` (lifecycle only, same capability): inline **200** `{dry_run, result: {rolled, dropped, errors}}` = would-roll/would-drop counts, writes nothing, takes no lease; other kinds → **422** |

### Findings — read (M6)

All session-auth, no capability (reads). All take the filter family (`cluster_id` **required**,
`scanner`, `severity`, `state`, `namespace`, `image_repo`, `image_digest`, `cve_id`, `package_name`,
`assignee`, `kev`, `fixable`, `disagree`, `ptype`, `present`, `new_within_days`, `overdue`, `unassigned`, …) and the global `as_of`. `severity` values are the **full-word canonical vocabulary**
(D46/#274: `critical|high|medium|low|negligible|unknown`) served by the server-derived
`severity_canonical` key — facet bucket keys are the same words; the verbatim scanner word stays
display-only in rows. `ptype` (M8d/#241) is also a facet (pre-v4 rows bucket as
`"unknown"` until a sweep heals them, D30) and a group dim — and unlike `kev`/`epss` it IS
recorded on occurrences, so it stays filterable/facetable at a past `as_of` (v3-era rows are
explicitly `null` there). `overdue=true|false` (issue #363) filters on the **materialized D21 group
clock** (`sla_clock_at`) against cutoffs derived from the **live SLA policy at query time** — a
policy edit moves the filter instantly, chip ≡ filter by construction (shared handled-states set,
KEV fast-lane included); works on grid/facets/groups/exports, and at a past `as_of` it filters the
reconstruction's own read-time verdict (judged at `now=T`, never the cache field). Multi-page grid
walks freeze the cutoffs in the cursor (the PIT freezes docs, the query freezes with them).
**Unassigned (issue #349 §1):** `unassigned=true|false` is ABSENCE, not negation — an owner is a NON-EMPTY `assignee` (a cleared one is written as `""`, which `exists` alone would count as owned). It is a distinct filter because the excludes below are pure `must_not`, so `exclude_assignee=bob` keeps unowned rows and can never ask "nobody owns this". It is also a facet (a `filter` agg over the grid's own clause, so the rail count equals the filtered rows) and is answerable at a past `as_of` from the reconstruction.

**Negation (issue #349, completed by #492):** every filterable term has an exclude mirror —
`exclude_severity`, `exclude_state`, `exclude_scanner`, `exclude_assignee`,
`exclude_image_repo`, `exclude_namespace`, `exclude_ptype`, `exclude_cve_id`,
`exclude_package_name` — compiled to `must_not` clauses. Semantics are **pure
must_not**: a row *missing* the field survives the exclusion (`exclude_assignee=bob` keeps
unassigned rows; `exclude_package_name=zlib` keeps OS-level rows that carry no package at
all). A field is include OR exclude, never both (422). Mirrored on `ExportParams`
and `ViewPreset`; at a past `as_of`, excludes on recorded fields apply and
`exclude_image_repo` is a 422 like its include twin.
`image_digest` deliberately has **no** exclude twin — it is a drill-down identity, not a
browsing facet (issue #492 ruling).

**`package_name` (issue #492):** an EXACT keyword term, both directions — the fuzzy reading of
a package name is what `q` already does (it wildcards across `package_name` among other
fields) and stays include-only. It is a filter, **not** a facet: `fields=package_name` on
`/findings/facets` is a 422, because a rail dim over unbounded package cardinality is not a
browsing surface. Recorded on occurrences, so it filters at a past `as_of` too.
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
| GET | `/api/v1/findings/top-components` | Top packages by finding rows with per-scanner unique-CVE counts (Overview card; now-only — 422 at a past `as_of`) |
| GET | `/api/v1/trends/scans` · `/api/v1/trends/findings` | Time series from scan-events over `days` (1–365, default 30); `/scans` also takes `interval=day\|hour` (hour only for `days` ≤ 31, else 422 — audit 343); `resolved_semantics: "scan_resolved"` (A-m9 — *scan-observed* resolution, not human `state=resolved`). `/findings` also takes `split=scanner\|severity` (severity = the D16 server-derived canonical, six buckets; **now-only** — 422 at a past `as_of`) and an optional `scanner=trivy\|grype` query-filter scope (M9c 1b) |
| GET | `/api/v1/trends/ingest-failures` | Pushes the ingest route refused **after the token check** per bucket, one series per scanner (issue 575; the same records `/scanners/ingest-failures` pages, so a series sums to that route's `total` for the same window). Same axis as `/trends/scans` — `days` (1–365, default 30), `interval=day\|hour` (hour only for `days<=31`, else 422) — so the two strips line up. An append-only log: a past `as_of` just ends the window at T (no 501). `{series: {<scanner>: [{date, count}]}, days, interval}`; a cluster with no refusals is `series: {}` |
| GET | `/api/v1/contributors` | Triage-work leaderboard + TTR/SLA-hit from `system-audit-log` (FR-15) over `days` (1–365, default 30). `totals` (M9d slice 3) = the team KPI block: exact team-wide `by_action` (top-level agg, never board-capped), **pooled** median TTR / SLA-hit (never median-of-medians), `critical_cleared`; same block at a rewound `as_of` |
| GET | `/api/v1/contributors/export.csv` | The leaderboard as CSV (issue 359): the SAME payload `/contributors` serves, so the file can't disagree with the screen. Fixed columns — the five measures + one `action_<name>` per action of the closed triage vocabulary, present as `0` rather than absent in a quiet window. Cells CSV-injection-sanitized (the actor is a username: attacker-controlled). **Not** a PIT sweep — the rows are the terms agg, already bounded by the 100-actor board, so the `JAVV_EXPORT_MAX_ROWS` **413** is a post-count backstop (no cheap pre-count exists) and there is no PIT-slot 429. `as_of` rides the read's D28 seam, not the findings export's flat 501 |
| GET | `/api/v1/scanners/freshness` | Per-(cluster, scanner) `last_ingest_at` + `silent_for_seconds` (FR-6/D20 banner; #218). Max across tokens; disabled tokens count; never-ingested → nulls |
| GET | `/api/v1/scanners/ingest-failures` | One scanner's pushes the ingest route refused **after the token check** (issue 357; INDEX-MAP `javv-ingest-failures-*`), newest first. `?scanner=` is **required**, so no page or total ever mixes scanners; `days` (1–365, default 30) + optional `as_of` are the trend window — an append-only log, so a past `as_of` just ends the window at T (no 501). `size` 1–100 (default 25), cursor-paged by `search_after` **without a PIT** (a record written mid-walk lands ahead of the cursor). `{data, total: {value, relation}, next_cursor}`; each row: `@timestamp`, `failure_id` (also on the backend's `ingest rejected` log line), `scanner`, `stage`, `reason`, `status`, `error`, `image_ref`. Tampered cursor → 422 |
| GET | `/api/v1/scanners/provenance` | Per-(cluster, scanner) versions/`effective_config` of the latest **committed** run + last-N runs (`?runs=`, ≤50). Catalog-first (R-CATALOG); latest = max `scan_order`, never `@timestamp` (M8c/#240) |
| GET | `/api/v1/audit` | The journaled history, plain-session read (M8c/#240): filters `entity_type`/`action`/`actor` (each with an `exclude_*` twin — issue 349 negation; a row missing the field survives its exclusion, so `exclude_actor` keeps actor-less system rows), ordered `(@timestamp, event_id)` (`?order=`, desc default), same opaque-cursor paging + A-m1 semantics as `/findings`. `as_of` (M9d/D28) bounds the walk at a rewound T — absent/`now` = unbounded. Rows are **decorated at read** (M9d): `finding`/`decision` sub-objects carry the touched entity's identity (cve/image/scanner/type), `null` once the doc ages out — history stays untouched, decoration is display-only and tenant-checked per doc (SEC-4) |
| GET | `/api/v1/audit/facets` | Rail counts for the audit screen (M9d): `entity_type`/`action`/`actor` terms aggs under the same filters (incl. `exclude_*`) + `as_of` bound as the walk. `interval=day\|hour` + `window_days` adds `activity` — the audit lens's events-over-time histogram (quiet buckets as zeros) |
| GET | `/api/v1/audit/export.csv` | Streaming CSV of the audit lens (M9d, same filters incl. `exclude_*`): decorated + CSV-injection-sanitized, constant-memory PIT sweep; > `JAVV_EXPORT_MAX_ROWS` → **413**, PIT cap → **429** (same bounds as the findings export) |
| GET | `/api/v1/images` | Running images = the latest **committed** inventory run's image docs (M8c/#240; the T=now case of M8b's `running_images_at` — shared primitives). Partial runs never leak; clean (zero-finding) images appear; `inventory: null` = no committed inventory yet (unknown ≠ empty) |
| GET | `/api/v1/images/timeline` | One `repo:tag`'s committed scan-event history (`cluster_id` + `image_repo` + `tag` query params) for the image-detail digest sub-timeline — build-change (digest flips) and per-scanner gap markers derive client-side |
| GET | `/api/v1/clusters` | Cluster listing (D-5): token-derived `cluster_id`s ∪ registry names ∪ retirement records (a cluster whose delete stopped halfway has only that left, and stays listed under `include_retired` so the delete can be retried); `cluster_name` defaults to the id. **Display-only** — never a query key. Each row carries `retired`; retired clusters (issue 765) are left out unless `?include_retired=true`. A retirement that a newer accepted scan has outlived already reads as not retired. Each row also carries `last_scan_at` (the newest accepted scan; null when none) and its retirement schedule (ISO datetimes): `silent_since`, where the countdown starts (the newest accepted scan, else the first token's mint, or the cluster's return from retirement when that is later; null when nothing is known), `warns_at` and `retires_at` (null = never retires), `delete_started` (issue 778: a delete of this cluster started and has not finished; delete it again), and `retirement_mode` (issue 778: `manual` or `auto` while retired, else null; a manual retire revoked the tokens, so bringing it back needs a newly minted one) |

**Cursor errors (A-m1):** expired PIT → **410** (re-run the search); tampered/invalid cursor →
**422**; OpenSearch transport failure → **503**. The PIT slot is released on every error path.

### Findings — triage & decisions (M5b/M5c/M5d)

| Method | Path | Capability | Purpose |
|---|---|---|---|
| PATCH | `/api/v1/findings/{finding_key}/triage` | `can_triage` | One VEX-model transition (`state` ∈ open/acknowledged/not_affected/risk_accepted/resolved; `vex_justification` required iff `not_affected`); CAS'd on the doc; journaled (D17) |
| POST | `/api/v1/findings/bulk-triage` | `can_triage` | **Bounded-synchronous** (A-Mc): frozen selector set ≤ `JAVV_BULK_INLINE_LIMIT` (5000) applies now; above → **413**; selector materializing > `JAVV_BULK_MAX_TARGETS` (10000) → **413** "selector too broad". Empty selector → 422. One journal row per action |
| POST/GET | `/api/v1/decisions` | `can_triage` | Create / list decisions (ignore-rules etc.). **Immutable + lifecycle stamp** — edit = revoke+new. `risk_accepted` type additionally requires `can_accept_audit_final` (SEC-2 → 403 without it). `expiry` is a bare date (`YYYY-MM-DD`) or a timezone-aware datetime; a datetime is stored and returned in UTC, so `…T23:00:00+02:00` comes back as `…T21:00:00+00:00` (issue 706). The list takes `cve_id`, `include_revoked` (default false) and `size` (≤500, default 50) / `offset` (≤10000) |
| PATCH | `/api/v1/decisions/{decision_id}` | `can_triage` | The revoke+new edit (one `effective_at`/`operation_id`, D40) |
| POST | `/api/v1/decisions/{decision_id}/revoke` | `can_triage` | Revoke (projection un-applies) |
| GET | `/api/v1/decisions/approvals` | `can_accept_audit_final` | The approvals queue (security-lead view): ACTIVE risk-accepts, soonest expiry first, `size`/`offset` paging. Slice 4b filters, all server-side: `q` (CVE contains) · `status` (`active\|expiring\|expired\|open-ended`, derived from `expiry` at query time against `warn_days`, default 7 — mirrors the UI chip) · `created_by` · `scanner` (`both\|trivy\|grype`, the column value), each with an `exclude_*` twin (issue 349 negation — the vocabularies partition the queue, so excluding `expiring` yields the other three statuses, open-ended included; exclusions never lift the revoked-row guard). Response carries `facets` (status/created_by/scanner counts under the same lens) |
| GET | `/api/v1/decisions/approvals/export.csv` | `can_accept_audit_final` | The queue as CSV (issue 359, absorbing #373): the SAME lens the queue read runs, every filter above honoured incl. the `exclude_*` twins and `warn_days`. Streaming, constant-memory PIT sweep with **CSV-injection-sanitized** cells (the `justification` is approver-authored free text). > `JAVV_EXPORT_MAX_ROWS` → **413** from a cheap pre-count before any PIT; PIT cap → **429** — the same bounds as the findings/audit exports. Gated like the queue, **not** session-only: the rows name who accepted which risk. Two columns differ from the screen on purpose — `status` is the chip's verdict **derived per row** at the same boundaries the `status` filter uses (chip ≡ filter ≡ facet ≡ export), and `scope_namespaces`/`scope_images` carry the raw lists rather than the screen's truncating "+2" label (both empty = cluster-wide). Revoked acceptances never appear, whatever the lens |

### Settings (M5d)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/settings/sla` | session | Read SLA policy (`critical_days`/`high_days`/`medium_days`/`low_days`/`kev_days` — full-word settings, D46/#274) |
| PUT | `/api/v1/settings/sla` | `can_manage_settings` | Replace SLA policy |
| GET | `/api/v1/settings/staleness` | session | Effective D20 timers for `?cluster_id` (its override if set, else the fleet default) + `per_cluster_override` (M9e) |
| PUT | `/api/v1/settings/staleness` | `can_manage_settings` | Replace the timers; `cluster_id` in the body writes the per-cluster override, absent = the fleet default. Journaled (D17) |
| GET | `/api/v1/settings/retirement` | session | The effective cluster retirement window for `?cluster_id` (its override if set, else the fleet default, else 45 days) + `per_cluster_override` (issue 765). `retire_after_days: null` = never; `warn_days` = how long before retirement the warning starts. Until a value is saved, the env seeds `JAVV_CLUSTER_RETIRE_AFTER_DAYS` / `JAVV_CLUSTER_RETIREMENT_WARN_DAYS` |
| PUT | `/api/v1/settings/retirement` | `can_manage_settings` | Set `retire_after_days` (required; `null` = never) and `warn_days` (required); `cluster_id` in the body writes the per-cluster override, absent = the fleet default. A window not longer than the effective scanner-down timer, or a `warn_days` not shorter than the window → **422**. Journaled (D17) |
| GET | `/api/v1/settings/scan-scope` | session | The D-2 session read of `?cluster_id`'s scan scope (the bearer `GET /api/v1/scan-scope` stays scanner-only; M9e) |
| PUT | `/api/v1/scan-scope` | `can_manage_settings` | Replace a cluster's scan scope (D43/FR-24: empty include = all, ignore wins). Journaled (D17) |
| GET | `/api/v1/settings/data` | `can_manage_retention` | The Data & OpenSearch panel's one read: effective lifecycle settings for `?cluster_id` (+ `per_cluster_override`), report TTL, the effective findings-cleanup window for `?cluster_id` (+ `findings_cleanup_override`), snapshot repo ref (M9e) |
| PUT | `/api/v1/settings/retention` | `can_manage_retention` | Set `retention_days` (RMW of the lifecycle doc; `cluster_id` in body = the per-cluster override). Journaled (D17) |
| PUT | `/api/v1/settings/rollover` | `can_manage_retention` | Set `max_age_days`/`max_docs`/`max_size_gb` (same doc/override rule). Journaled (D17) |
| PUT | `/api/v1/settings/report-ttl` | `can_manage_retention` | Set the export TTL `hours` (fleet-wide `report_ttl` setting — row 11 made `JAVV_EXPORT_TTL_HOURS` runtime-editable). Journaled (D17) |
| PUT | `/api/v1/settings/findings-cleanup` | `can_manage_retention` | Set the D37/M12 long `cleanup_days` window — fleet default, or a per-cluster override via body `cluster_id` (the lifecycle-settings pattern; consumed per cluster by the findings-cleanup job). Journaled (D17) |
| PUT | `/api/v1/clusters/{cluster_id}/name` | `can_manage_settings` | Rename a cluster's display name (M8c/#240): journaled per D17 (journal-first), stored in the `system-config` `cluster-registry` doc via a seq_no-CAS write. `cluster_id` itself is immutable |
| POST | `/api/v1/clusters/{cluster_id}/retire` | `can_manage_settings` | Retire a cluster (issue 765): it leaves the default listing, so the switcher and All clusters; its data is kept and its tokens are revoked. Journal-first (D17): a `cluster_retire` row, then a `token_revoke` row per token. Unknown cluster **404**, already retired **409**. Returns `{cluster_id, retired, retired_at, by, mode}` |
| DELETE | `/api/v1/clusters/{cluster_id}` | `can_manage_retention` | Delete a **retired** cluster (issue 765): everything JAVV holds for it but its audit rows. In order: its token docs (a scanner still pushing gets 401), its five history series as whole-index drops matched by exact name (with an index auto-created under the alias's own name), its rows in `findings`, `javv-scan-watermarks`, `javv-scan-orders`, `system-decisions`, `system-notifications` and `system-reports` (with their chunks), its `system-config` docs and registry name, then its retirement record, so a delete that stopped halfway can be retried, and last it stamps the `cluster-delete:<cluster_id>` marker it wrote before its first step as finished (issue 778). The marker stays as a tombstone: the nightly retirement sweep re-runs the data steps for a deleted cluster nothing names any more, removing rows a push in flight wrote after the delete (`javv_cluster_delete_leftovers_total`), and drops it after a second clean pass, or at once if the cluster was onboarded again. Journal-first (`cluster_delete`). Not retired **409**, unknown **404**, a step that could not finish, or the store away or overloaded, **503** (retry it; counted in `javv_cluster_delete_incomplete_total`, logged at `warning`). Returns `{cluster_id, deleted: {<what>: count}}`. Snapshots taken before still hold the data |
| POST | `/api/v1/clusters/{cluster_id}/unretire` | `can_manage_settings` | Bring a retired cluster back to the listing (`cluster_unretire`, journal-first). Its revoked tokens stay revoked: a scanner needs a new token. The record is kept with `returned_at`, and the retirement countdown restarts from it. Unknown **404**; not retired, or a concurrent retire landed first, **409**; a delete of it started and has not finished, **409** "its delete did not finish: delete it again" (issue 778: its tokens and part of its data are gone) |

### Saved views (M8e, C-6)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/views` | session | List saved views — visible to **all** authenticated users (C-6; per-view ACLs post-MVP). Card counts come from `/findings/facets` at render time, never stored |
| POST | `/api/v1/views` | session | Save a view (`owner` = principal, immutable). `preset` mirrors the findings filter family 1:1 (incl. the issue-349 `exclude_*` family, same no-mixing rule) and is validated against the **closed vocabularies** (lowercase canonical severities incl. `negligible`, the 6 states, scanner, ptype shape) — garbage → 422, never stored. Schema v2 (M9f slice 4) adds `workbench` `{columns, dense, sort, order, window_days}` — the findings-table capture, cluster-agnostic by shape (no `cluster_id`/absolute `t` representable). Journaled (D17, journal-first) |
| PATCH | `/api/v1/views/{view_id}` | session, **owner-or-admin** | Edit name/description/preset/workbench (partial; preset and workbench each replace whole). Non-owner without `can_manage_settings` → 403 (the IDOR case); `owner` is unrepresentable in the body. seq_no-CAS write → **409** on a concurrent edit. Journaled |
| DELETE | `/api/v1/views/{view_id}` | session, **owner-or-admin** | Delete (204). Journal row carries the frozen doc, so deleted views stay auditable |

### Exports (M6) & scheduled reports (M7)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/findings/export.csv` | session | Streaming, **CSV-injection-sanitized** export of any lens. > `JAVV_EXPORT_MAX_ROWS` (50k) → **413** (narrow the lens or schedule) |
| GET | `/api/v1/findings/export.vex` | session | OpenVEX/CycloneDX per **one scanner** (`scanner` required — per-scanner is sacred); same row cap |
| POST | `/api/v1/reports` | session · `kind: bulk_triage` → `can_triage` | Enqueue a scheduled job. `kind: export` is session-only *by design* (a scheduled export is a read). `kind: bulk_triage` is gated like the inline bulk (`can_triage`; + `can_accept_audit_final` for risk-accepts) — the selector **freezes to `target_ids` at enqueue**, and the inline 5000 ceiling is lifted (only the 10k freeze cap applies → **413**) |
| GET | `/api/v1/reports/{report_id}` | session (owner) | Job status (public view — never leaks `params`/`attempt_id`/lease fields). 404 unknown **or not yours** (a foreign `report_id` is indistinguishable from missing). For a `done`, unexpired report also mints the short-lived (15 min) signed `download_token` — refetch for a fresh one |
| GET | `/api/v1/reports/{report_id}/download` | session (owner) + `token` | Streams the result chunks in order (CSV or VEX JSON). **410** past `expires_at` (re-run the export) · 404 no result yet · 403 bad/stale token |
| GET | `/api/v1/notifications` | session | The bell (FR-16, polled — no broker): own notifications only, newest 50, + server-computed `unread` count. Types: `report_ready`, `sla_breach`, `assignment`, and `cluster_retiring` (issue 765: written by the retirement sweep for every user holding `can_manage_settings` when a cluster enters its warning window, once per silence (a settings change that moves the dates sends nothing new); `ref` is its `retires_at`, the first sweep from then retires it. The sweep deletes them again when the cluster scans again, or a return from retirement starts a new silence; a settings change keeps them, and a retired cluster's stay) |
| PATCH | `/api/v1/notifications/{notification_id}/read` | session | Mark one of **your own** read — anyone else's id is 404 (IDOR-indistinguishable from missing) |
| DELETE | `/api/v1/notifications/{notification_id}` | session | Dismiss (hard-delete) one of **your own** feed docs — same own-or-404 gate; 204 on success (M9f slice 3) |

Exports + search cursors share a **per-principal concurrent-PIT cap**
(`JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL`, 10) → **429 + `Retry-After`** past it. Scheduled-report
results are stored in OpenSearch chunks with `expires_at` (default 24 h); the drain worker
(`python -m backend.jobs.report_drain`; the backend runs it on `JAVV_JOB_REPORT_DRAIN_CRON`, every
5 minutes by default) claims jobs via OCC + fencing
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

**Logging of rejections** (issue 523). Every rejection increments `javv_ingest_rejected_total{reason}`.
Every rejection after the token check (`400`, `403`, `413`, `422`, `503`) also logs one `ingest rejected`
warning with `reason`, `status`, the token's `cluster_id` and `scanner`, and `failure_id` (the id of
the failed-ingest record below, so a table row and its log line join), plus `limit_bytes` on a
`413`, `errors` on a `422`, and `payload_cluster_id` / `payload_scanner` on a `403`. The token itself is
never logged. A `429` logs at most one warning per token per minute. A `401` is counted only, because
an unauthenticated sender could otherwise choose how much the backend writes to its log.

**Recording of rejections** (issue 357). The same post-token rejections are also written as one doc
each to `javv-ingest-failures-<cluster_id>` (INDEX-MAP), under the **token's** cluster and scanner,
for the scanner-status failed-ingests table. The `401` and the `429` record nothing, for the same
reason they don't log per request. The response is unchanged by recording: if the write fails, the
scanner still gets the same status and body, and the backend logs `ingest failure not recorded`
(with the `failure_id`) and increments `javv_ingest_failures_unrecorded_total{reason}`, because the
table cannot show its own gaps.

## Metrics (`/metrics`, Prometheus)

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `javv_ingest_accepted_total` | counter | `scanner` | Envelopes accepted + committed |
| `javv_ingest_rejected_total` | counter | `reason` | Envelopes rejected — `reason` ∈ `bad_token`, `rate_limited`, `too_large`, `bad_gzip`, `bad_json`, `invalid_envelope`, `scope_mismatch`, `storage_error` |
| `javv_ingest_failures_unrecorded_total` | counter | `reason` | Post-token rejections whose failed-ingest record could not be written (issue 357) — non-zero means the scanner-status failed-ingests table is missing rows. `reason` ∈ the six post-token values above |
| `javv_ingest_findings_written_total` | counter | `scanner` | Finding docs written |
| `javv_http_request_duration_seconds` | histogram | `method`, `route`, `status` | Route-TEMPLATE labels (unrouted → one `unmatched` series); `/metrics` + probes excluded (#220 M-1) |
| `javv_opensearch_request_errors_total` | counter | `kind` | `conn`, `timeout`, `429`, `503` — dependency failures on read + bulk paths (M-2) |
| `javv_opensearch_backoff_retries_total` | counter | — | Per-item 429/503 bulk retries — the saturation signal (the only flow control without a broker) |
| `javv_sla_clock_missing_total` | counter | — | Findings pages that held at least one row without a materialized `sla_clock_at` (issue 363). Those rows' SLA clock is computed by the per-pair aggregation instead, and the page also logs a `warning`. A sustained rate means the store needs the `rebuild_state` job to backfill the field |
| `javv_cas_conflicts_total` | counter | `site` | `watermarks`, `scan_orders`, `reproject` (+ `report_claim`, M7 slice 2; `retirement`, issue 765: an un-retire that lost to a concurrent retire) — multi-writer contention early warning (M-3) |
| `javv_limit_rejections_total` | counter | `limit` | `pit_cap`, `export_rows`, `bulk_targets`, `bulk_inline` (M-4) |
| `javv_pits_open` | gauge | — | Open PIT slots (per pod, like the guard) |
| `javv_export_rows_total` / `javv_export_bytes_total` | counter | `format` | What was **actually** streamed (a disconnected client counts what it got) |
| `javv_auth_failures_total` | counter | `reason` | `bad_credentials`, `locked_out`, `expired_session`, `missing_capability` — never a username label (M-5) |
| `javv_config_warnings_total` | counter | `setting` | Start-ups whose settings leave the OpenSearch connection weaker than it looks (issue 715): `JAVV_OPENSEARCH_VERIFY_CERTS` (certificates not checked on `https`) or `JAVV_OPENSEARCH_URL` (a password over plain `http`). Each also logs one `warning` at start. |
| `javv_stored_setting_unknown_fields_total` | counter | `setting` | Stored-setting reads that dropped fields this release doesn't know (issue 640). Non-zero after a rollback means a newer release saved that setting; the log warns once per setting doc per process, and this keeps counting. `setting` is the kind (`sla`, `scan_scope`, `snapshot_repo`, `report_ttl`, `lifecycle`, `findings_cleanup`, `staleness`, `retirement`, `cluster-retirement`), never the per-cluster doc id |
| `javv_job_runs_total` | counter | `kind`, `outcome` | Background-job runs started by the scheduler (issue 691). `kind` is one of the eight in `jobs/registry.py`; `outcome` is `done`, `failed`, or `skipped` (another backend held the lease). A `failed` rate is a job that keeps failing; no `done` for a kind over its schedule is a job that is not running |
| `javv_job_last_success_timestamp_seconds` | gauge | `kind` | Unix time of the kind's last successful scheduled run in this process; `0` until one succeeds after a restart. Alert on `time() - value` against the kind's schedule |
| `javv_scheduler_tick_errors_total` | counter | — | Scheduler ticks that failed before a job could start, in practice the store being away. A sustained rate means no job is running |
| `javv_cluster_retirement_held_total` | counter | | Retirement sweeps that retired nothing because no cluster had a scan accepted within its scanner-down timer (issue 765). That points at JAVV itself, an outage or a rejected scanner version, not at the clusters; each also logs one `warning` |
| `javv_cluster_delete_incomplete_total` | counter | | Cluster deletes that stopped halfway and answered 503 (issue 765): a step stayed contended, or the store was away or pushing back. A retry finishes the delete; each also logs one `warning` |
| `javv_cluster_delete_leftovers_total` | counter | | Deleted clusters whose next-night pass (the retirement sweep) found rows written after the delete, a push in flight or a job running at the time, and removed them (issue 778). Each also logs one `warning` |
| `javv_cluster_delete_recheck_failures_total` | counter | | Retirement sweeps whose pass over deleted clusters failed (issue 778). The run's retirements stand and the next run passes again. Each also logs one `warning` |
| `javv_cluster_retirement_notify_failures_total` | counter | | Retirement sweep steps whose bell notifications could not be written or withdrawn (issue 765). The run's retirements stand and the run records as done; the next run tries again, repeating no notification still in the bell. Each also logs one `warning` |

Plus the default `prometheus_client` process/GC gauges. The scrape is **storage-free** (no
OpenSearch call) — it keeps working during an outage, exactly when it's needed. Single-process
registry (one uvicorn worker); multi-worker needs the multiprocess mode (noted in
`core/metrics.py` for M10). SLO/alerting rules on top are **owned by M10**
(`prometheus-rules.yaml`).

### Client events (issue 453)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/client-events` | session | Browser `warn`/`error` telemetry → the backend's own stdout stream (**204**, fire-and-forget). Body `{events: [{level, event, fields}]}`, 1–20 events, `extra="forbid"`. `level` is a `Literal['warn','error']`, so `debug`/`info` are **unrepresentable** (422), not filtered. **No storage, no index, no audit row** — the stream IS the destination |

Two properties defend the stream against its own untrusted input, both by construction:

- **Namespaced names.** Every event re-emits as `client.<name>`, so a client posting
  `event: "scan done"` can never collide with a real backend event — an operator's `grep`, or an
  alerting rule keyed on an event name, cannot be fooled. `client_event=true` + `username` are
  tagged too, but they only help a reader who filters on them; the namespace helps one who doesn't.
- **Nested fields.** Client keys ride under a single `fields` key, never splatted as siblings, so
  `fields: {"username": "admin"}` cannot forge the line's attribution. The redaction processor
  recurses in, so `token`-ish keys and `Bearer …` values are masked inside the blob as well.

Shape caps (batch ≤ 20, ≤ 25 keys/object, depth ≤ 3, keys ≤ 64 chars, values ≤ 512 chars, lists ≤
20, and the event-name pattern `^[a-z0-9][a-z0-9 ._-]{0,63}$`) are the **schema** — violations are
422 and owe no metric. Only the **per-principal rate cap** is a bounded path in the ops-parity
sense: over it → **429** + `Retry-After` + `LIMIT_REJECTIONS{limit="client_events"}` + a warning
(setting `JAVV_CLIENT_EVENTS_RATE_LIMIT_PER_MINUTE`). The limiter runs *after* body validation on
purpose — it bounds what reaches the log stream, and a rejected batch emits nothing.

RBAC: **registry-exempt**, not capability-gated — any authenticated user's browser reports its own
events, so "without the capability → 403" is unrepresentable. The regime it carries instead (401
anonymous, 403 on a `must_change` session, the rate cap) is asserted in `test_client_events_route`.

## Logging

Structured JSON via the **shared `libs/javv-common` structlog pipeline only** (observability.md
§1). Every request binds a `request_id` (from `X-Request-ID` if well-formed — `[A-Za-z0-9-]{1,64}`
— else minted; echoed in the `X-Request-ID` response header and, on every non-2xx including a
500, in the error body's `request_id`); ingest also binds `cluster_id`/`scanner`. An unhandled
exception logs one `error` line, `unhandled error`, with the stack, `method`, `path` and the same
`request_id`. uvicorn's own duplicate traceback is filtered out (issue 644). The
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
