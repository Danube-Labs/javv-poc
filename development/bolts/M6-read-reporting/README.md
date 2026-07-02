# M6 - Read/reporting + VEX export + as-of-T

**Status:** tracked in [#31](https://github.com/Danube-Labs/javv-poc/issues/31) — live status on the GitHub issue/board

## Goal
PIT+search_after search (faceted by scanner, composite aggs); trend endpoints over scan-events; expanded Contributors; streaming sanitized CSV; VEX export (OpenVEX/CycloneDX); the as-of-T read path — T=now short-circuits to materialized current-state. (T<now historical reconstruction is delivered by M8b's `as_of_t` composition; M6 delegates to it, and the full whole-app time-travel UI is gated on M8b.)

**Canonical refs:** [`PLAN_v4 §8 M6`](../../../docs/engineering/V4/PLAN_v4.md) · `SPEC_v4` (FRs for M6) · [`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (indices touched).

## Depends on
M3, M4, M5c, M5b (system-audit-log — Contributors + audit-log replay read it). The T<now
time-travel portion additionally depends on M8b (`as_of_t`) — gated, not a blocker for M6's T=now core.

## Deliverables
The actual files/modules this bolt creates — **in the layered tree, not here** (paths proposed):
- `backend/app/query/search.py` — faceted PIT + `search_after` finding search (FR-12); filters by severity/state/scanner/assignee/KEV/fix-available/disagree; `from/size` only under 10k, PIT+`search_after` for deep paging (delete the PIT in `finally`).
- `backend/app/query/aggs.py` — scanner-faceted aggregations; capped `terms` or **composite** aggs paginating via `after_key` (FR-12, NFR pin §). Pure DSL-builder, unit-tested on the emitted body.
- `backend/app/query/trends.py` — trend endpoints over `javv-scan-events-*` (FR-5/FR-12; "new in 30d"); per-`cluster_id`, always-applied filter.
- `backend/app/query/contributors.py` — **Contributors (expanded)** over `system-audit-log`: resolved-over-time, median TTR, SLA-hit %, leaderboard (FR-15). Reads M5b's audit log.
- `backend/app/api/search.py` — GET search/agg/trend/contributors endpoints; `extra="forbid"` request models; `cluster_id` via the one `tenant_search` chokepoint (SEC-4), entitlement on every fetch **and export** (IDOR). Follow [`standards/api-design.md`](../../standards/api-design.md) (paths/naming, opaque `next_cursor`, `as_of` param, response shape).
- `backend/app/export/csv_stream.py` — streaming, **CSV-injection-sanitized** export from any lens, constant memory (FR-13 inline "run now" path); PIT+`search_after`, small pages.
- `backend/app/export/vex.py` — **VEX export** serializing `state`/`vex_justification` → OpenVEX + CycloneDX, consumable by Trivy/Grype `--vex` (FR-22 export-only; import → v1.1).
- `backend/app/query/as_of.py` — the **as-of-T dispatcher**: `T=now` short-circuits to materialized current-state (M3 cache); `T<now` **delegates to M8b's `backend/app/query/as_of_t.py`** (does NOT reimplement reconstruction — D28/FR-23 boundary).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test, not a promise):
- **T=now short-circuit:** every read endpoint with `T=now` reads the materialized current-state cache and **never** touches the append-log reconstruction path (assert no occurrences/audit-replay query is issued) — D28.
- **T<now delegates:** a `T<now` request routes to M8b's `as_of_t` (asserted at the seam); M6 contains no reconstruction logic of its own.
- Faceted search paginates deep results via PIT+`search_after` with the PIT deleted in `finally`; aggregations are **scanner-faceted** and never aggregate on `text` fields.
- Composite aggregations paginate correctly via `after_key` (no silently-capped buckets).
- **CSV export is injection-sanitized** (leading `=,+,-,@,\t,\r` neutralized) and streams in constant memory (no full-result buffering).
- **VEX export** round-trips a triaged finding's `state`/`vex_justification` into valid OpenVEX **and** CycloneDX that a Trivy/Grype `--vex` consumer parses (golden).
- Contributors metrics (TTR/SLA-hit %/leaderboard) compute from `system-audit-log` (M5b), not from live findings.
- Every read/agg/export carries an explicit `cluster_id` filter via the `tenant_search` chokepoint (negative test: cross-tenant leak is impossible — SEC-4/IDOR).

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** search/agg/trend **DSL-builders** (assert emitted body incl. scanner facet + composite `after_key`); CSV sanitizer (each dangerous leading char); VEX serializer shape (OpenVEX + CycloneDX); the as-of-T **dispatch decision** (`T=now` → cache, `T<now` → delegate).
- **Integration (real OpenSearch):** PIT+`search_after` deep paging with PIT cleanup; faceted aggregations over seeded multi-scanner findings; trends over seeded `scan-events`; Contributors over seeded `system-audit-log`; `cluster_id` isolation by unique tenant.
- **Golden fixtures:** VEX export — a checked-in triaged finding → expected OpenVEX **and** CycloneDX documents (validated against a `--vex` consumer); a streaming-CSV fixture with injection-bait cell values → expected sanitized output.

## Out of scope (defer)
- **T<now historical reconstruction** → M8b (`as_of_t` composition: occurrences ≤ T ⋈ decisions-active-at-T + audit-log replay ≤ T + `javv-images` ≤ T). M6 only delegates.
- The **whole-app time-travel UI** (global picker rewinding every screen) → gated on M8b + M9c.
- **VEX import** → v1.1.
- Scheduled/throttled large exports + the `system-reports` queue → M7.
- Historical **all-clusters** dashboards → v1.1 `javv-metrics` rollup (limited until then).

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).
