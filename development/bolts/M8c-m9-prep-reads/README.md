# M8c - M9-prep session reads (audit · provenance · inventory · cluster registry)

**Status:** tracked in #240 — live status on the GitHub issue/board (label `bolt`)

## Goal
Four thin, session-gated, read-only endpoints over data the backend already writes, so every M9
screen has a shipped data source. Falls out of the v5 design rulings (#237,
`handoff/v5/docs/SCREENS-v5.md` BLOCKED register). Pure reads — no new index (the D-5 registry is
one *document* in the existing `system-config`).

**Canonical refs:** [`PLAN_v4 §8 M8c`](../../../docs/engineering/V4/PLAN_v4.md) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (`system-audit-log`, `javv-scan-events`,
`javv-images`/`javv-inventory-runs`, `system-config` — read-only) · decisions D32 (audit shape),
D37/R-CATALOG (latest = via commit catalog), D39/D40 (`inventory_order`, committed-only), D41/D44
(provenance + `effective_config` stamps), D-5 ruling (cluster registry) ·
[`SCREENS-v5`](../../../handoff/v5/docs/SCREENS-v5.md) §§1, 7, 10–12, 13.2/13.8

## Depends on
- Nothing unshipped. Must **check overlap with M8b** before building the inventory read — it is
  the `T=now` special case of M8b's point-in-time API; spec them to share the query layer, not
  collide.

## Deliverables
- `backend/src/backend/routers/audit.py` — `GET /api/v1/audit?cluster_id=…&entity_type=…&actor=…&cursor=…`:
  **plain session** (ruled 2026-07-07), cursor-paged (existing PIT machinery), ordered
  `(@timestamp, event_id)`, filters on `entity_type`/`action`/`actor`. Feeds the M9d Audit screen
  + Contributors activity feed.
- Scanner provenance read (extend `routers/scanners.py`): per `(cluster, scanner)` the **latest
  committed** scan-event's `scanner_version` / `scanner_db_version` / `scanner_db_built` +
  `effective_config` + last-N runs (counts, durations). Latest goes **through the commit catalog**
  (R-CATALOG), never latest-doc. Feeds Scanner status (M9d) + Settings→Scanning (M9e).
- `backend/src/backend/routers/images.py` — `GET /api/v1/images?cluster_id=…`: rows from the
  latest **complete** inventory run (`status=committed`, ordered by `inventory_order`); per-image
  repo/tag/namespace/replicas/first-last-seen. Clean images (zero findings) MUST appear. Feeds
  Running images (M9c) + the All-clusters Replicas column.
- Cluster registry: seed/read a `system-config` cluster-registry doc (`cluster_id` +
  `cluster_name`) + `GET /api/v1/clusters`; rename write (admin, `can_manage_settings`,
  journaled per D17). `cluster_name` is display-only — **never a query key** (hard constraint).
- RBAC/IDOR registry rows for every new route · `docs/API.md` rows (same PR) ·
  `docs/CONFIGURATION.md` if any knob appears (none expected).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**:
- Every new read carries the explicit `cluster_id` filter through the tenancy chokepoint (test per route).
- Provenance read proven catalog-first: a newer *uncommitted* scan-event never surfaces (test).
- Inventory read returns only the latest **complete** run: a partial/running inventory never leaks (test).
- Audit read ordering `(@timestamp, event_id)` pinned by test; cursor 410/422 semantics match A-m1.

## Tests to write
- **Unit:** query-builders for all four reads (filters, sort, paging clauses).
- **Integration (real OpenSearch):** tenant isolation per route; catalog-first provenance;
  committed-only inventory; zero-findings image present; registry rename journaled + visible.
- **Golden fixtures:** none new — reuse existing scan-event/inventory fixtures.

## Out of scope (defer)
- Point-in-time (`T<now`) variants of these reads → M8b.
- Any write beyond the registry rename; notifications (M7 slice 3 / D-3); scan-scope session read (M9e / D-2).

## Updates
- **2026-07-08 · slice 1 (audit + provenance)** — `GET /api/v1/audit` (`query/audit.py` +
  `routers/audit.py`): plain-session, fixed `(@timestamp, event_id)` pair-sort in ONE direction
  (`?order=`, desc default — replay stays asc in `query/human_at.py`), A-m1 machinery reused
  verbatim (`encode_cursor`/`decode_cursor` from `query/search.py`; a findings cursor is rejected
  as an audit cursor via the `s` field), per-principal PIT slots (A-m12). `GET
  /api/v1/scanners/provenance` extends `routers/scanners.py`: latest = terms-on-scanner +
  `top_hits` sorted on the exact `scan_order` long (a scan-events doc IS the commit marker, so
  scan-events reads ARE committed-only by construction — the DoD "uncommitted never surfaces"
  test plants ghost occurrence rows with a newer order and proves them invisible); last-N runs =
  composite over `(scanner, scan_run_id)` with sum/min/max sub-aggs (dates are epoch-ms < 2^53 —
  exact in metric aggs) + the run's exact order via `top_hits` `_source`, sorted in Python
  (**never a `max` agg on `scan_order`**, #257 — pinned by an adjacent-giant-orders test at
  ~1.75e18). No registry rows needed: both reads are non-mutating (the registry gates mutations);
  slice 2's rename registers under `can_manage_settings`.

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
