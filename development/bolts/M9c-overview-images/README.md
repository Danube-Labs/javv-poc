# M9c - Overview / all-clusters / images (+ point-in-time image view)

**Status:** tracked in [#37](https://github.com/Danube-Labs/javv-poc/issues/37) — live status on the GitHub issue/board

## Goal
Dashboards and the image surface: the **Overview** (current-state severity/trend summaries), the
**all-clusters** view, and **per-image drill-down** with a Trivy/Grype scanner dropdown and per-scanner
finding table — fully **time-travelable** via the global picker (FR-14/FR-23), including the
**point-in-time image view** (per-digest sub-timelines: which CVEs on which digest at T). All numbers come
from server-side aggregations / M8b reconstruction; nothing is computed client-side.

**Canonical refs:** [`PLAN_v4 §8 M9c`](../../../docs/engineering/V4/PLAN_v4.md) (line 677) ·
`SPEC_v4` FR-12 (dashboards), FR-14 (per-image report, time-travelable), FR-23 (whole-app rewind +
**all-clusters cost guardrail**) · [`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md)
(`javv-scan-events` trends; `javv-finding-occurrences` for as-of-T; **`javv-metrics-*` is v1.1/deferred,
no bolt**) · decisions D28 (rewind), D38/M16 + D39/M11-r2 (historical all-clusters limited in MVP).
AUDIT item folded in: **I3** (`javv-metrics` deferred to v1.1; all-clusters/historical degrades gracefully).

## Depends on
- **M9b** — shell, filter module, findings components (the image table reuses finding rows / disagreement
  views; per-scanner sacred).
- **M8b** — point-in-time query API: forward ("digest X at T") + the symmetric two-step catalog query;
  `runtime_inventory_at_T` vs `vulns_as_scanned_at_T` (kept distinct, FR-14).

## Deliverables
Files this bolt creates — **in the layered tree, not here** (paths proposed):
- `frontend/src/views/OverviewView.vue` — current-state KPIs + trend charts (single-cluster default).
- `frontend/src/views/AllClustersView.vue` — cross-cluster current-state roll-up; **degrades for `T<now`**
  (see DoD / Out-of-scope).
- `frontend/src/views/ImageDetailView.vue` — per-image (`image_digest`) drill-down; Trivy/Grype **scanner
  dropdown**; per-scanner verbatim-severity finding table (reuses M9b components); `repo:tag`→digest nav (F3).
- **Charts (ECharts, per FE rules):**
  - `frontend/src/components/charts/SeverityTrendChart.vue`, `OverviewSummaryChart.vue` — use
    `shallowRef` + `markRaw` for the ECharts option/instance; **manual ECharts module imports** (no full bundle).
  - `frontend/src/charts/buildSeverityTrendOption.ts`, `buildOverviewOption.ts` — **pure option-builders**
    (data → ECharts option). Primary unit-tested surface.
- **Query/param builders (pure):**
  - `frontend/src/charts/buildTrendQuery.ts` — trend params from `javv-scan-events` (`cluster_id`, range, `T`).
  - `frontend/src/images/buildImageAtTQuery.ts` — emits the M8b two-step params: `runtime_inventory_at_T`
    (latest `status=committed` inventory-run ≤ T by `inventory_order`) and `vulns_as_scanned_at_T`
    (max-`scan_order` committed run ≤ T, then occurrences via R-CATALOG). **Kept as two distinct results,
    never conflated** (D38/H6).
- `frontend/src/components/images/DigestSubTimeline.vue` — per-digest sub-timeline; marks "image build
  changed here" rather than a silent gap (F3); "not yet scanned then" when no committed snapshot ≤ T.
- `frontend/src/components/dashboards/LimitedHistoricalNotice.vue` — the **graceful-degradation banner** for
  all-clusters-historical (I3): "Historical all-clusters view is limited until the v1.1 metrics rollup."
- `frontend/src/stores/overview.ts`, `frontend/src/stores/images.ts` — Pinia state, both reading global `T`.

## Definition of Done
Everything in [`definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each a gate):
- **PLAN gate (point-in-time image):** moving the global picker to a past `T` reconstructs an image's exact
  CVE list + as-of-then severities (via M8b); a **clean rescan reads as clean at T, not the prior snapshot**;
  a digest that dropped CVE-Y by T does **not** appear (false-positive guard). Proven by tests against M8b.
- **`runtime_inventory_at_T` vs `vulns_as_scanned_at_T` never conflated** — the image view shows both as
  distinct facts; "not yet scanned then" state when no committed snapshot ≤ T (FR-14).
- **Server-side everything:** every dashboard number is a server aggregation / M8b result; charts only
  render what the server returns. No client-side summing across scanners (per-scanner sacred).
- **ECharts hygiene:** `shallowRef`+`markRaw` for options/instances; manual module imports (asserted by a
  bundle/import check or lint rule).
- **I3 graceful degradation (explicit):** single-cluster current-state + per-cluster rewind work fully;
  **all-clusters-historical (`T<now`) shows `LimitedHistoricalNotice`, not an error or a wrong/expensive
  query.** All-clusters **current-state** (`T=now`) works. No code path attempts a historical all-clusters
  raw-occurrences scan.

## Tests to write
See [`testing.md`](../../standards/testing.md). FE rule: **unit-test option-builders + emitted query params
as pure units** (Vitest).
- **Unit (pure, primary):**
  - `buildSeverityTrendOption` / `buildOverviewOption` — data → exact ECharts option (series, axes, severity
    colors from tokens). Deterministic; the contract.
  - `buildTrendQuery` — `cluster_id` + range + `T` → exact emitted params.
  - `buildImageAtTQuery` — emits the **two distinct** M8b queries (inventory-at-T, vulns-as-scanned-at-T);
    asserts they are never merged; `T=now` vs `T<now` branch.
  - **I3 guard (unit):** the all-clusters store, given `T<now`, returns the `limited` state and **emits no
    historical all-clusters query** (asserted on the emitted-params mock).
- **Component:** `DigestSubTimeline` marks build-change vs gap vs not-yet-scanned; `ImageDetailView` scanner
  dropdown swaps the per-scanner table without merging; `LimitedHistoricalNotice` renders for all-clusters `T<now`.
- **Integration (optional, against M8b):** as-of-T image reconstruction matches a known sequence.
- **Playwright:** time-travel E2E deferred to M9f — note only.

## Out of scope (defer)
- **`javv-metrics-*` rollup → v1.1 (locked; I3 + INDEX-MAP).** No bolt builds it in MVP. Therefore
  **historical all-clusters dashboards are limited/unavailable in MVP** (D38/M16, D39/M11-r2); this bolt
  ships the graceful-degraded state, not the rollup. Cheap multi-year all-clusters trends arrive with the
  v1.1 metrics rollup, read from the rollup (not raw occurrences).
- Audit/approvals/contributors/scanner-status → M9d. Settings (Data & OpenSearch, staleness) → M9e.
- Streaming/scheduled export from a lens → M6/M7 (export dialog wiring); cross-cutting empty states → M9f.

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Updates
- **2026-07-07 — backend↔UI drift rulings (major audit #224, 05 §B/§C):** **(B-1)** there is no
  `package_type` field — the packageTypes donut is **cut for MVP** (leave the layout slot; post-MVP
  enhancement issue if wanted); **(B-6)** `languageBinaries[]`/`topComponents[]` widgets have no
  backing aggregation — cut for MVP; **(C-5)** historical **all-clusters** dashboards are
  limited/unavailable until the v1.1 metrics rollup (D39 ruling) — the screen states this rather than
  showing wrong numbers; cluster list = distinct `cluster_id`s from data; **[DECIDE at kickoff]
  (D-5)** where the relabelable `cluster_name` lives (recommend: a small `system-config` doc — a tiny
  backend addition) or MVP shows raw ids.

- **2026-07-05 (pre-kickoff, from the first e2e smoke — #156 finding 3):** the `javv-images` docs
  have **no `image_ref` field** — the tag is stored split as `image_repo` + `tag` (e.g. `nginx` +
  `1.21.6`). Image views must read/compose from those two fields (or this bolt adds a derived
  `image_ref` at read time); anything expecting a combined `image_ref` gets null today.

- **2026-07-07 — v5 design rulings (#237):** contract = `SCREENS-v5.md` §§1–2, 7–8. **B-1 ruled:
  the Overview package-type donut is KEPT** per the v4 design — backed by **M8d** (`ptype` facet);
  placeholder state until M8d + one sweep. The All-clusters list + `cluster_name` come from the
  **M8c cluster registry** (D-5 ruled: `system-config` doc). Running-images Replicas/first-last
  seen come from the **M8c inventory read** (`GET /api/v1/images`, latest complete run — clean
  zero-finding images must appear). Depends-on grows: M8c, M8d.

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
> **Frontend analog (M9a+):** `logger` from `frontend/src/lib/logger.ts` — structured, leveled,
> backend-shaped lines; raw `console.*` in app code is ESLint-banned. Threshold: `VITE_LOG_LEVEL`
> ([CONFIGURATION.md §2b](../../../docs/CONFIGURATION.md)); never log tokens/cookies/bodies (NFR-5).
