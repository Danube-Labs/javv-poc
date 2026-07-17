# Screens — javv (v5, refreshed against the shipped backend)

> **Living UI contract** (formerly `SCREENS-v5.md` in `handoff/v5/docs/` — suffixes dropped 2026-07-16, #410).
> Layered over the frozen `handoff/v4/` prototype (the DESIGN.md §8 fidelity source).

Refresh of `handoff/v4/docs/SCREENS.md` against the **shipped** contract (`docs/API.md`, through
M7 slice 1) and the drift rulings (`05-backend-ui-drift-m9.md`). Information architecture, brand,
tokens, and layout are preserved from v4 (`DESIGN_SYSTEM.md` / `ui-foundations.md` bind all values);
only ruling-forced changes are made. Every screen names its **bolt** (M9a–M9f READMEs).

Conventions used below:
- **Data** = concrete calls (method + path + key params from API.md). `cluster_id` is **required on
  every read** (tenant chokepoint, D38/H9). The global `as_of` (`T`) rides on every read; `T=now`
  omits it.
- **Every number on every screen is a server aggregation** — the client never counts, sums, or
  pages locally. Per-scanner counts are **sacred**: Trivy and Grype numbers are never summed,
  averaged, or merged, anywhere.
- Severity values in filters/aggs are **lowercase** and include a **`negligible`** bucket (A-1);
  display may uppercase. States are the **6-state** set (A-2); every "now" list is implicitly
  `present=true`.
- **Capability gating** reads `capabilities` from `GET /auth/me` — never role names (A-4). A
  `must_change` session is routed to the password screen; everything else 403s.
- **DECIDE flags: ALL RULED 2026-07-07** (operator, #237) — see the RESOLVED register at the
  bottom. Where a ruling flipped the drawn recommendation (B-1 donut kept, C-6 views server-side)
  the sections below are amended in place.
- **BLOCKED: needs backend** items are now **scheduled**: the pre-M9 backend bolts **M8c**
  (session reads: audit log · scanner provenance · inventory · cluster registry), **M8d**
  (envelope `ptype`), **M8e** (server-side saved views).

---

## Global chrome (bolt: **M9a**)

Layout unchanged from v4: sidebar (226px slate, lockup → All clusters, grouped nav, footer health
chip + version line) + topbar (cluster switcher · time picker · global search · bell · avatar).
Place the real brand SVGs (`brand/lockup.svg`, dark variants in dark chrome) — never approximated.

**Data**
- `GET /auth/me` — `username`, `role`, `capabilities`, `must_change`. All gating flows from
  `capabilities` (A-4). Nav items whose screen is capability-gated (Approvals, admin Settings
  sections) are **hidden** without the capability.
- `GET /readyz` (polled) — drives the global **degraded banner** ("Search backend unavailable —
  check OpenSearch health"); any API `503` envelope raises it too; auto-clears on `200`.
- `GET /api/v1/scanners/freshness?cluster_id=…` — per-(cluster, scanner) `last_ingest_at` +
  `silent_for_seconds`; drives the **ScannerFreshnessBanner** ("data as of T; scanner silent
  since T′") and the sidebar sweep-health chip. Never-ingested → nulls → "no data yet" chip, not
  an error.

**Time picker (C-1, D28/FR-23).** Two visibly distinct controls in one group (V4-DELTA conflict 4):
the **time-travel `T`** (Now / rewind / jump-to-date → amber "Viewing history — as scanned at T"
banner + Back to now) and the **trend window** (relative to `T`, scopes charts + Contributors).
- State: **picker-set-but-unsupported** — if M8b hasn't landed, `T<now` reads return `501`; show
  the banner "History available after M8b", keep `T=now` fully working. (Check milestone order at
  M9a kickoff; currently M8→M9 makes this moot.)

**States:** degraded (banner, chrome stays up, data areas show degraded placeholders — never
blank); scanner-silent (freshness banner); must_change (locked to password change).

**Changed vs SCREENS.md**
- Capability gating replaces the 5-role matrix everywhere (A-4).
- Freshness banner is now a concrete endpoint call (D-1, shipped).
- Time-travel unsupported state added (C-1).
- Bell behavior moved to M9f (see Notifications, below) and gains export-expiry affordances (C-2).

---

## 0. Login & password change (bolt: **M9a**)

**Data:** `POST /auth/login` (generic 401 — no user-existence hint; `429` lockout after
`JAVV_LOGIN_MAX_ATTEMPTS`), `POST /auth/password` (the only mutating route a `must_change` session
may call), `POST /auth/logout`, `GET /auth/me`.
**States:** bad-credentials (generic copy), locked-out (429 — "try again later", no countdown
oracle), forced password change (SEC-6: bootstrap admin / temp password).
**Changed:** copy states capability-based access; SSO/OIDC removed (post-MVP, per V4-DELTA).

---

## 1. All clusters (bolt: **M9c**)

Fleet landing page; layout preserved (KPI strip → cluster table with MixBar).

**Data**
- Cluster list: **RULED (D-5/C-5, 2026-07-07)** — the `system-config` cluster-registry doc
  (`cluster_id` + relabelable `cluster_name`) ships in **M8c** with its session read; the UI
  renders display names from it. Until M8c lands this stays blocked.
- Per-cluster severity mix + KPI strip: `GET /api/v1/findings/facets?cluster_id=<id>` — one call
  per cluster row; buckets are **per-scanner** — the MixBar renders one bar per scanner (or a
  scanner toggle), never a merged bar.
- Health chip + Last sweep: `GET /api/v1/scanners/freshness?cluster_id=<id>`.

**States:** loading (skeleton rows); empty (no clusters registered — cold-start copy); degraded;
**T<now → `LimitedHistoricalNotice`**: "Historical all-clusters view is limited until the v1.1
metrics rollup" (C-5/D39) — the current-state table is replaced by the notice, never a wrong or
expensive query.

**Changed vs SCREENS.md**
- Fleet KPI strip severity buckets: lowercase + `negligible` (A-1); per-scanner, never summed.
- Historical all-clusters explicitly limited (C-5).
- Cluster name source ruled: `system-config` registry (D-5 → **M8c**).
- "Replicas" column: fed by the **M8c** inventory read (see Running images).

---

## 2. Overview — single cluster (bolt: **M9c**)

**Data**
- KPI strip (severity cards + Fix-coverage): `GET /api/v1/findings/facets?cluster_id=…` —
  severity buckets (lowercase; `negligible` shown muted, see DECIDE below) + `fixable` bucket.
  Cards remain click-through → Findings pre-filtered (deep-link preset preserved).
- Vulnerabilities over time: `GET /api/v1/trends/findings?cluster_id=…&range=…` — faceted by
  scanner (two series sets, never merged). Note: `resolved_semantics: "scan_resolved"` — any
  "resolved" series is **scan-observed** resolution, labeled as such (A-m9).
- Scan activity: `GET /api/v1/trends/scans?cluster_id=…&range=…`.
- Per-namespace table: namespace buckets from `GET /api/v1/findings/facets` (rows → Findings
  filtered by ns; deep-link preserved).

**Cut / changed widgets**
- **Package-type donut — RULED (B-1, 2026-07-07): KEEP, per the v4 design.** Backed by the
  **M8d** envelope change (`ptype` field + facet bucket). Until M8d lands + a rescan cycle
  repopulates, the donut shows the "awaiting package-type data" placeholder; pre-M8d findings
  aggregate as `unknown` ptype until re-observed by a scan.
- **Top components** + **Language-specific binaries** tables — **cut** (B-6, no backing agg);
  layout slots left.
- **Newly published** bar chart — **cut** (B-2: no `published` field exists); slot reused by the
  scan-activity trend.

**States:** loading (skeletons per card); empty/first-run ("no sweep has landed yet"); degraded;
scanner-silent banner; `T<now` history banner (single-cluster rewind is fully supported once M8b
lands; 501-state before that, C-1).

**Changed vs SCREENS.md:** A-1 (lowercase + negligible), B-1 (donut kept, fed by M8d ptype),
B-2/B-6 (widget cuts), A-m9 (trend semantics label), C-1 (time-travel states). Scanner-type
filter stays (it maps to the `scanner` filter param).

---

## 3. Findings — the core grid (bolt: **M9b**)

Layout preserved: facet rail + toolbar (FilterBar + Save view + ColumnsMenu) + bulk bar + table.

**Data**
- Rows: `GET /api/v1/findings?cluster_id=…&severity=…&state=…&scanner=…&namespace=…&image=…&cve_id=…&kev=…&fixable=…&disagree=…&as_of=…` —
  PIT + `search_after` paged; response = rows + opaque `cursor`. Every "now" query implicitly
  `present=true` (A-2).
- Facet counts: `GET /api/v1/findings/facets` with the same filter family — **per-scanner
  buckets rendered per scanner, never summed** (FR-12).
- "Images affected" column: `GET /api/v1/findings/groups?cluster_id=…&group_by=cve` (B-4 — the
  count is a group aggregation, not a field; **verify the exact agg shape at M9b kickoff**, else
  extend `/findings/groups`).
- Triage writes: see Finding detail. Bulk: `POST /api/v1/findings/bulk-triage` (frozen selector;
  `413` past `JAVV_BULK_INLINE_LIMIT`/`JAVV_BULK_MAX_TARGETS` → "narrow the selection" copy;
  `422` empty selector).

**Facet rail** (top→bottom): Severity (critical/high/medium/low/**negligible**/unknown — muted
treatment for negligible+unknown, never red) · Scanner (trivy/grype) · Attributes (KEV /
Fix available / Scanners disagree) · State (**6**: open, acknowledged, not_affected,
risk_accepted, resolved, stale) · Assignee (incl. Unassigned) · Namespace · **Package type**
(returns per B-1 ruling — buckets from the M8d `ptype` facet; hidden until M8d lands).
> **RULED (A-1, 2026-07-07):** `negligible` IS its own muted bucket — Grype emits it; hiding it
> breaks "counts sum". Display muted grey, never red.

**Table columns:** checkbox · Vulnerability (`cve_id`, mono) · Severity (verbatim word, display
uppercase) · EPSS (raw `epss` 0–1 bar; **Grype rows only**, em-dash on Trivy — B-3: no
percentile) · KEV · Component (`app`) · Package (`package_name`) · Current (`installed_version`) ·
Fixed (`fixed_version`) · Scanner (+ `±` badge when `disagree=true`; tooltip severities come from
the sibling-scanner row, A-3) · Images (group agg, B-4) · SLA (server-computed deadline/overdue —
B-5, **never client math**; field names verified at M9b kickoff) · State (6-state pill) ·
Assignee.

**Paging:** cursor-based (PIT + `search_after`) — the pager is **next/prev over server cursors**
with rows-per-page (10/25/50); total from the server agg. Numbered random-access pages from v4 are
dropped (contract is cursor paging).

**States**
- loading — skeleton rows; empty/first-run — "no sweep yet" friendly state; filtered-empty —
  "no findings match" + clear-filters.
- **410 cursor expired** (A-m1) — silently re-run the search from the current filters; toast if
  the position was lost. **422 tampered cursor** — reset to first page. **503** — degraded state
  in the grid area + global banner.
- **429 PIT cap** (`JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL`) — "too many open searches/exports,
  retry in Ns" honoring `Retry-After`.
- 403-capability-hidden — bulk-triage bar and row checkboxes absent without `can_triage`.
- Bulk 413 — inline error offering to narrow the selection.
- Zero-vs-nonzero scanner pair (M9b update, #156-4): one scanner's 0 is **never** a green "clean"
  check while the other reports findings — the pair renders side-by-side with disagreement
  weight.

**Changed vs SCREENS.md:** A-1 (lowercase + negligible), A-2 (6 states + implicit
`present=true`), A-3 (disagree is a bool; tooltip queries sibling row), B-1 (ptype column/facet
KEPT per ruling — after M8d), B-3 (raw EPSS only), B-4 (images count = agg), B-5 (SLA
server-computed), A-m1 (cursor error states), C-2 (export entry point → Export dialog, below).

---

## 4. Finding detail + triage (bolt: **M9b**)

Layout preserved: back-link → header → `grid-2-1` (evidence stack left, sticky triage panel
right).

**Data**
- The finding row (all real fields, see DATA_MODEL) from `GET /api/v1/findings?cluster_id=…&cve_id=…&image=…` —
  and the **sibling-scanner row** from the same call without the `scanner` filter: that pair IS
  the per-scanner evidence table (A-3/B-2 — "no black box, no merge").
- Triage: `PATCH /api/v1/findings/{finding_key}/triage` — body `{state, vex_justification?,
  assignee?, notes?}`; `vex_justification` (CISA five) **required iff** `state=not_affected`;
  CAS'd, journaled (D17).
- Decisions on this CVE: `GET /api/v1/decisions?cluster_id=…&cve_id=…` (active / revoked
  struck-through / expired). Risk-accept: `POST /api/v1/decisions` (type `risk_accepted`
  additionally requires `can_accept_audit_final` — SEC-2 → 403 without); edit =
  `PATCH /api/v1/decisions/{id}` (revoke+new, D40); revoke = `POST …/revoke`.

**Header/meta — renders what exists (B-2/B-3):** CVE mono h1, severity tag (verbatim word), KEV
tag, meta line = CVSS float · raw EPSS (Grype rows only) · first seen (`first_seen_at`) · last
seen. **Cut:** description prose, CVSS vector, CWE, reference links, published date, EPSS
percentile — none exist; deep CVE metadata is a post-MVP NVD enrichment. The left column leads
with the **per-scanner evidence table** instead.

**Triage panel (6-state VEX, A-2):** open · acknowledged · not_affected (reveals CISA-five
justification chips; component/code-not-present chips labeled "False positive") · risk_accepted
(**read-only here** — comes from the scoped risk-accept dialog, with a manage pointer) ·
resolved (manual) · stale (**system-set, read-only** + "re-scan to refresh"). Fixed-vs-stale
explainer kept. Assignee (`assignee`, Assign to me / Reassign) + Notes (escaped, never rendered
as HTML). **Removed:** Impact / Action / Approver / Task free-text fields (V4-DELTA conflict 1 —
the model is state + justification + notes + structured decisions).

**SLA box:** server-computed deadline + overdue flag from the findings read (B-5).

**States:** loading; 403-capability-hidden (triage controls disabled-with-tooltip without
`can_triage`; risk-accept without `can_accept_audit_final`); CAS conflict on save → "changed by
someone else — reload and retry" (no silent overwrite); `T<now` — panel read-only ("viewing
history"); `present=false` row visible **only** in history views (A-2).

**Changed vs SCREENS.md:** A-2 (6 states + justification flow), A-3 (evidence = sibling query),
B-2/B-3 (metadata cuts), B-5 (server SLA), V4-DELTA-1 (old triage fields removed), D40
(decision edit = revoke+new).

---

## 5. Export dialog + scheduled reports (bolt: **M9b** wiring; download/bell states **M9f**)

Reachable from Findings/Overview/Images "Export".

**Data**
- Run now: `GET /api/v1/findings/export.csv?<current lens params>` (streaming, CSV-injection
  sanitized). VEX: `GET /api/v1/findings/export.vex?scanner=<one>&…` — **`scanner` required**,
  one scanner per file (per-scanner sacred).
- Schedule: `POST /api/v1/reports` (`kind: export`, session-only by design — A-6). Status:
  `GET /api/v1/reports/{report_id}`. Download: `GET /api/v1/reports/{id}/download` — **M7
  slice 3, not shipped yet**; until it lands the "schedule" path is **BLOCKED: needs backend
  (planned, M7 slice 3)**.

**States (C-2 — all drawn):** run-now streaming progress · **413 over
`JAVV_EXPORT_MAX_ROWS` (50k)** → "narrow the lens or **schedule off-peak**" (switch tab) ·
scheduled-pending → bell on done · **"expires in Xh"** on the bell item and the download row
(`JAVV_EXPORT_TTL_HOURS`, default 24 h) · **410 expired** → "download expired — re-run the
export" · 429 PIT cap with `Retry-After`.

**Changed vs SCREENS.md:** C-2 (TTL/expiry affordances + 410 state — new), A-6 **RULED
(2026-07-07): export stays session-only** — available to every authenticated user; the v4
"Viewer cannot export" matrix row is dropped. A `can_export` capability is parked as a tracked
idea (issue), deliberately not scheduled.

---

## 6. Saved views (bolt: **M9f**; backend in **M8e**)

Card grid preserved.

> **RULED (C-6, 2026-07-07): server-side.** Saved views are a selling point — they must be
> durable and shareable. New `system-views` index + CRUD endpoints ship in **M8e**
> (INDEX-MAP + MAPPING_VERSION + bootstrap + RBAC rows + API.md). The **owner column returns**
> (v4 design); views are visible to all authenticated users, mutable by their owner (+admin).

**Data:** `GET/POST /api/v1/views` · `PATCH/DELETE /api/v1/views/{view_id}` (**M8e**, session;
mutations owner-or-admin). The per-card **live count** is
`GET /api/v1/findings/facets?<view's filter params>` (server agg — fetched lazily per visible
card; never counted client-side). Card → Findings with the filter preset (deep-link round-trip
must reproduce identical query params).

**States:** empty ("save a filter set from Findings"); count-loading per card; degraded (counts
show em-dash); 403 on mutating someone else's view (edit/delete affordances hidden unless owner
or admin).

**Changed vs SCREENS.md:** C-6 ruled server-side (M8e); owner column kept per the v4 design.

---

## 7. Running images (bolt: **M9c**)

**Data**
- Per-image severity mix + finding counts: `GET /api/v1/findings/groups?cluster_id=…&group_by=image&…`
  — per-scanner counts side-by-side + the `trivy_count`/`grype_count`/`count_delta`
  count-disagreement pair (D5b; per-image, distinct from per-finding `disagree` — V4-DELTA
  conflict 7). Facets for the rail via `GET /api/v1/findings/facets`.
- Inventory metadata (replicas at last sweep, app, first/last seen): **scheduled — M8c**
  inventory read (latest complete `inventory_run_id`, `status=committed`, ordered by
  `inventory_order`). M8c must check overlap with M8b's point-in-time API first (this read is
  the `T=now` special case).
- Image naming: compose from `image_repo` + `tag` (no `image_ref` field exists — M9c update,
  #156-3).

**Columns:** Image (`image_repo` + registry mono) · Tag · Namespace · Replicas (M8c inventory
read) · per-scanner finding counts (`T n / G n / Δ` — never a merged total) · Severity mix
(labeled MixBar, per scanner) · Scanners · Last seen.

**States:** loading; empty/first-run; **scanner-silent** banner ("Inventory as of T; scanner
silent since…"); **last-run-incomplete** banner ("showing the last complete inventory"); `T<now`
history banner; degraded. Never shows partial/stale inventory as live (V4-DELTA).

**Changed vs SCREENS.md:** A-3/D5b (count-disagreement pair per image), B-1 (ptype facet after
M8d), #156-3 (repo+tag composition), inventory read scheduled (M8c).

---

## 8. Image detail — point-in-time (bolt: **M9c**)

Identity is the **content digest** (`image_digest`). Layout preserved: header → scanner dropdown
("Showing results from Trivy|Grype") → per-scanner severity cards → findings table.

**Data**
- Per-scanner findings: `GET /api/v1/findings?cluster_id=…&image=<digest>&scanner=<sel>&as_of=…`;
  severity cards from `GET /api/v1/findings/facets` with the same params (one scanner's buckets
  only — the dropdown swaps, never merges).
- "Two questions" cards + Build-history digest sub-timeline (`runtime_inventory_at_T` vs
  `vulns_as_scanned_at_T`, kept as two distinct facts): **M8b point-in-time API — not shipped**;
  until M8b these render the C-1 "history available after M8b" state. `T=now` per-scanner
  findings work today.

**States:** loading; **"Not yet scanned then"** (T before the first committed scan); build-changed
marker (never a silent gap); scanner-silent; degraded; C-1 pre-M8b state for any `T<now`.

**Changed vs SCREENS.md:** scanner dropdown is a **read** lens only (no version anything — D41);
EPSS/KEV null on Trivy rows enforced here too (V4-DELTA-5); M8b dependency made explicit (C-1).

---

## 9. Approvals → Decisions queue (bolt: **M9d**)

Re-pointed from the old justification/impact/action shape to **`system-decisions`** (V4-DELTA
conflict 2).

**Data:** `GET /api/v1/decisions/approvals?cluster_id=…` — **gated by
`can_accept_audit_final`; the nav item is hidden without it** (403-capability-hidden). Row detail
+ actions: `GET /api/v1/decisions`, `POST /api/v1/decisions/{id}/revoke`,
`PATCH /api/v1/decisions/{id}` (revoke+new, D40).

**Columns:** CVE (mono) · type · **scope** (images and/or namespaces; empty = cluster-wide) ·
justification · approver · **expiry** (expired decisions resurface) · status (active / revoked
struck-through / expired) · when. Row → finding detail's "Decisions on this CVE".

**States:** loading; empty ("no pending decisions"); 403 (nav hidden); degraded.

**Changed vs SCREENS.md:** decisions shape replaces approval fields (V4-DELTA-2); capability
gate + nav hiding (A-4); revoke+new editing (D40).

---

## 10. Audit log (bolt: **M9d**)

Renders the structured D32 stream (A-5): `event_id`, `entity_type`
(finding/decision/token/user/settings/…), `action`, frozen `target_ids`, `revision`, ordered by
`(@timestamp, event_id)`; same-field edits order by `revision` (causal replay, D38/H8).

**Data:** **scheduled — M8c**: `GET /api/v1/audit?cluster_id=…&entity_type=…&actor=…&cursor=…` —
**plain session** (ruled 2026-07-07: read-only history of actions every user can already see;
Contributors already exposes derived views of it), cursor-paged, ordered `(@timestamp, event_id)`.
(Spec drawn against the D32 doc shape.)

**Layout:** facet rail (entity_type, action, actor) + filter bar + timeline table: When · Actor ·
entity_type+action tag pair · Target (frozen `target_ids`, rendered verbatim — never a
re-evaluated selector) · Detail. **Click-through only where `entity_type=="finding"`** (A-5).
Task column dropped (no field; Jira linkage is v1.1 — V4-DELTA-1).

**States:** loading; empty; degraded; retention note ("audit window bounded by
`system-audit-log` retention").

**Changed vs SCREENS.md:** A-5 (structured entity_type+action replaces the 8-string enum;
click-through rule; Task column dropped); endpoint scheduled (M8c).

---

## 11. Contributors (bolt: **M9d**)

**Data:** `GET /api/v1/contributors?cluster_id=…&range=…` (FR-15, shipped) — leaderboard +
TTR/SLA-hit computed server-side from `system-audit-log`. Scoped by the global trend window; the
"last 30 days" label follows the picker; window clamps to audit-log retention.

**Semantics label (A-m9):** any resolved-count series driven by trends carries
`resolved_semantics: "scan_resolved"` — label "scan-observed resolutions", distinct from human
`state=resolved` triage counts from the audit log. Don't conflate the two on one chart.

**Layout preserved:** team KPI strip → podium → leaderboard → resolved-over-time
(`GET /api/v1/trends/findings`, labeled per A-m9) → activity feed (from the M8c audit read —
same dependency as screen 10, feed only).

**States:** loading; empty (no triage activity in window); degraded; `T<now` fine (audit-log ≤T
is supported, C-1).

**Changed vs SCREENS.md:** A-m9 (resolution semantics label); activity feed blocked on the audit
read; severity colors stay firewalled from brand coral (unchanged rule).

---

## 12. Scanner status (bolt: **M9d**) — redesigned (C-3)

The v4 per-file ingest feed is gone. New composition per C-3:

**Per-(cluster, scanner) cards** — Trivy / Grype:
- **Freshness:** `GET /api/v1/scanners/freshness?cluster_id=…` — `last_ingest_at`,
  `silent_for_seconds` → health chip (ok / silent-N / never-ingested nulls → "no data yet").
- **Provenance (read-only, D41):** `scanner_version` · `scanner_db_version` · `scanner_db_built`
  from the latest committed scan-event — displayed as mono provenance lines with an
  "operator-managed (GitOps): change by swapping the image tag" affordance. **Never a control.**
  **Scheduled — M8c** provenance read (latest *committed* scan-event via the commit catalog;
  M9e's ScanningView shares the same read).
- **Last-N scan runs** (counts, durations): same M8c read.

**Trend:** `GET /api/v1/trends/scans?cluster_id=…&range=…` — scans over time per scanner
(replaces "ingested vs failed": accepted/rejected are Prometheus counters, not a UI API).

**Cut (A-7/D-4):** the Failed-ingests table and per-file retry/dead-letter feed — dead-lettering
is scanner-local by design; **do not build** a feed. The card links to the ops runbook instead.

**States:** loading; never-ingested; scanner-silent (chip + global banner agree); degraded;
`T<now` → "history for scanner status is limited until the v1.1 metrics rollup" (C-1/D39).

**Changed vs SCREENS.md:** C-3 (whole-screen redesign), A-7/D-4 (failed-ingest feed cut), D41
(version/DB lines are provenance display only), C-1 (historical limitation).

---

## 13. Settings (bolt: **M9e**; users/tokens panels also M9e)

Left sub-nav + panel + sticky save bar preserved — but the save bar appears **only on editable
sections**. Editable in MVP (C-4): **SLA policy · Users/Roles · Tokens · Scan scope · Data &
OpenSearch (retention) · Staleness timers**. Everything else is read-only display with an
**"operator-managed (GitOps)"** affordance.

### 13.1 Scan scope — editable (D43/FR-24)
**Data:** session read of the scan-scope doc — **D-2, planned, BLOCKED until it lands** (the
bearer `GET /api/v1/scan-scope` stays scanner-only; never widened). Write:
`PUT /api/v1/scan-scope` (M9e deliverable; capability-gated + journaled). Semantics fixed by
FR-24: empty include = all; ignore wins; fail-closed scanner fetch.
**Layout unchanged:** running-only toggle, include/ignore namespace lists, image globs, skipped
kinds.

### 13.2 Scanning — **read-only** (C-4, replaces v4's editable Scanners+Schedule+Vuln-DB)
Per-scanner cards display, from the latest committed scan-event's `effective_config` stamp
(D44, landed) + provenance (D41): running `scanner_version`, DB version/built (Trivy OCI /
Grype listing.json sub-tabs kept as **display**), effective tuning flags, applied scope.
**No version picker anywhere. No editable schedule/tuning.** Same M8c provenance read as
screen 12. Banner kept: "results kept per-scanner, never merged".
**Staleness timers** are the one editable control here (M3 backend shipped;
`PUT /settings/staleness` is the M9e deliverable — planned): `freshness_days` /
`scanner_down_days` + a banner-behavior preview.

### 13.3 SLA policy — editable (shipped)
**Data:** `GET /api/v1/settings/sla` · `PUT /api/v1/settings/sla` (gated `can_manage_settings`).
Days per severity (lowercase keys, incl. how negligible/unknown map — display note) + KEV
override hours.

### 13.4 Ignore rules → **Decisions** (redirect)
The v4 allowlist table is superseded by decisions (V4-DELTA-2): this section becomes a pointer
to the Decisions queue (screen 9) — decisions carry scope/justification/expiry/revocation.

### 13.5 Access & tokens — editable (shipped)
**Data:** `GET/POST /api/v1/admin/tokens`, `POST …/{token_id}/revoke`, `POST …/{token_id}/rotate`
(gated `can_manage_tokens`). Raw token shown **once at mint** (modal with copy affordance +
"you won't see this again"). Table: scanner scope, created, last_used, status.

### 13.6 Users & roles — editable (shipped)
**Data:** `GET/POST /api/v1/admin/users`, `PATCH …/{username}/role` (revokes their sessions —
confirm dialog says so), `PATCH …/{username}/disabled` (**409** on the last enabled admin —
inline error), `POST …/{username}/password-reset` (temp password + must_change) — all gated
`can_manage_users`. Reserved usernames `system`/`fleet` → 422 inline.
**Roles panel (A-4):** renders the 4 roles as **capability bundles** (viewer — none · triager —
can_triage · security_lead — + can_accept_audit_final · admin — *), from `system-roles` content.
The v4 5-role permission matrix is gone.
> **RULED (A-4, 2026-07-07): keep 4 roles.** A 5th can be seeded later as a `system-roles` data
> change, no migration.

### 13.7 Data & OpenSearch — editable (Admin)
Per-cluster retention days, rollover knobs, snapshot repo/schedule + manual snapshot/restore —
retention/rollover offered **only** for time-partitioned append families; the mutable family
(findings, watermarks, scan-orders, system-*) never gets a drop control.
**Data:** `PUT /settings/retention`, `PUT /settings/rollover`, `POST /snapshots`,
`POST /snapshots/{id}/restore` — **M9e deliverables, planned, BLOCKED until they land**; gated
`can_manage_retention` / `can_restore_snapshot` / `can_drop_index`, journaled.

### 13.8 Cluster
`cluster_id` immutable (mono). `cluster_name` **editable** — the D-5 registry doc was ruled in
(**M8c**); rename is a `system-config` write, journaled, display-only (never a query key).

**States (all sections):** loading; 403-capability-hidden (section hidden from sub-nav without
its capability); save-bar dirty/saved; degraded; 409/422 inline errors as noted.

**Changed vs SCREENS.md:** C-4 (Scanners/Schedule/Vuln-DB → read-only effective_config +
provenance; **`config.versions` selector removed — D41**), D-2 (scan-scope session read planned),
V4-DELTA-2 (ignore rules → decisions), A-4 (capability bundles replace the matrix), 13.7 new
(V4-DELTA Data & OpenSearch).

---

## 14. Notifications bell (bolt: **M9f**)

**Data:** `GET /api/v1/notifications` + mark-read PATCH — **D-3, planned (ships with M7
slice 3), BLOCKED until then**. Badge count is the server-computed unread count; polled (no
broker, NFR-9).
**Categories:** SLA-overdue-assigned-to-you · newly-assigned · **ready-export** — the export item
shows **"expires in Xh"** (C-2) and opens `GET /api/v1/reports/{id}/download`; on **410** the
item flips to "expired — re-run the export" (never a dead link).
**States:** loading; empty; 410-expired per item; degraded (badge pauses, no stale count).
**Changed vs SCREENS.md:** ready-export category + expiry/410 affordances (C-2/C-7); endpoint
BLOCKED (D-3).

---

## 15. Global search (bolt: **M9f**)

**Data:** three scoped, server-paged queries against the shipped read — no search endpoint is
invented: CVE match `GET /api/v1/findings?cluster_id=…&cve_id=<q>` · image match
`…&image=<q>` · namespace match `…&namespace=<q>`. Grouped dropdown (CVEs → finding detail;
images → image detail; namespaces → filtered Findings). Package-name search: the filter family's
coverage of `package_name` must be **verified at M9f kickoff**; if absent, that result group is
dropped (not client-filtered).
**States:** typing (≥2 chars); no-results; degraded.
**Changed vs SCREENS.md:** search = composed findings queries (server-paged), not a bespoke
endpoint; package group conditional.

---

## Cross-cutting (unchanged rules, restated)

- Deep-links pass presets into `useFilters` — presets now serialize **lowercase** severities and
  6-state values (A-1/A-2).
- RelTime everywhere; deadlines absolute. Esc/arrow keyboard patterns; coral focus rings.
- First-run/empty states on every data screen (M9f owns the shared components).
- Capability gating on every mutating affordance — from `/auth/me` capabilities (A-4); client
  gate is convenience, server is authority.
- All timestamps/IDs/versions in Space Mono; severity colors from the token map only; coral/amber
  never encode severity (ui-foundations).

## RESOLVED register (all six DECIDEs ruled by the operator 2026-07-07, #237)

| Id | Where | Ruling |
|---|---|---|
| A-1 | Findings rail, Overview KPIs | **Show** `negligible` as its own muted bucket |
| A-4 | Settings → Users & roles | **Keep 4** seeded roles (5th = later data change) |
| A-6 | Export dialog | **Session-only stays**; `can_export` parked as a tracked idea (issue, unscheduled) |
| B-1 | Overview donut, Findings facet/column | **KEEP the donut** per v4 design — envelope `ptype` ships in **M8d** |
| C-6 | Saved views | **Server-side** — `system-views` index + CRUD in **M8e**; owner column returns |
| D-5/C-5 | All clusters, Settings → Cluster | **Build** the `system-config` cluster registry — **M8c** |

## BLOCKED register (all scheduled)

| Screen | Needs | Scheduled |
|---|---|---|
| Export schedule download, Bell | `GET /api/v1/reports/{id}/download` · `GET /api/v1/notifications` + mark-read | **M7 slice 3** (D-3) |
| Settings → Scan scope | Session read of the scan-scope doc | **M9e** (D-2) |
| All clusters, Settings → Cluster | Cluster registry read (+ rename write) | **M8c** |
| Audit log, Contributors activity feed | `GET /api/v1/audit` (plain session, cursor-paged) | **M8c** |
| Scanner status, Settings → Scanning provenance | Latest committed scan-event read (provenance + effective_config + last-N runs) | **M8c** |
| Running images inventory metadata | Latest-complete-inventory read (replicas, seen) | **M8c** (check M8b overlap first) |
| Overview donut, Findings ptype facet/column | `ptype` in envelope + mapping + facets | **M8d** |
| Saved views CRUD | `system-views` index + `/api/v1/views` endpoints | **M8e** |
| Image detail point-in-time | M8b point-in-time query API | **M8b** |

## SHIPPED-DELTAS register (ruled deviations — the contract vs what was built)

Added 2026-07-16 (#410) so this contract and the app stop diverging silently. Every deviation
below was an **operator ruling against a built specimen** (recorded in the owning bolt README's
`## Updates` + its issue); this register is the one-hop index. The rule stands: a screen's
grammar is the prototype's — substituting it needs a live ruling (DESIGN.md §8.5).

| § | Contract said | Shipped | Ruling / record |
|---|---|---|---|
| 13.4 | Ignore rules → Decisions redirect stub | **No nav entry at all** — decisions live on `/approvals` + finding detail | 2026-07-15, M9e README (supersedes the #237 row-20 stub ruling) |
| — | (v4 prototype) per-CVE audit panel | **Struck** — no screen; the content ships on finding detail + Approvals + Audit | 2026-07-15, M9e README row 24 |
| 13.2 | (v4 prototype) scanner version select, tuning writes, enable toggles, Schedule section | **Read-only** provenance + `effective_config` cards; version = image-tag swap (D41), tuning = env/GitOps (C-4), no enable concept (D30), schedule = manifest | 2026-07-07 + 2026-07-15, M9e README §C |
| 13.2 | — | Namespace scope lists are **exact matches**; globs only on `exclude_images` | 2026-07-15, M9e README (verified in `scanner/scope.py`) |
| 13.3 | "Security Lead can edit" SLA | Edit gate is **`can_manage_settings`** (admin bundle) | M9e README row 5 |
| 13.6 | 5-role matrix, user delete | **4 capability bundles** (A-4), **disable-never-delete**, invite = temp password + `must_change` | M9e README row 8 |
| 13.7 | (v4 prototype) 4 editable per-purpose retention windows | **One** editable window over the 4 append families; protected families render read-only with the why written in the panel | 2026-07-15 ruling, M9e README row 23 |
| 13.7 | — | Panel additions beyond the contract: report/export-TTL knob (row-11 graduation), findings-cleanup window (D37/M12), read-only **OpenSearch runtime** card (§D), snapshots restore into `restored-*` copies only | M9e README rows 10/11 + §D |
| 13.8 | `schema_version: 3` | **4** (M8d ptype bump) | M9e README row 9 |
| global | FE freshness banner on a build-time env var | Banner + fleet chips read the **live staleness timers** (selected cluster's effective window); `VITE_FRESHNESS_BANNER_HOURS` removed | M9e README row 14 |
| global | — | Severity everywhere is the **six-word canonical vocabulary** (D46); verbatim scanner casing is display-only | D46/#274 |
| 2 | (v4 prototype had no Scan-activity card; the built one duplicated IngestLens) | Scan-activity card **dropped**; slot carries **Top components** (restored prototype card, ≤100-package server board w/ per-scanner unique-CVE counts, now-only read) + **Riskiest images** (ranked running images off the images read, rewindable) — both on the shared table skin + GridPager; Overview goes `wide` | 2026-07-16 §8.5 ruling on built specimens: **keep both** |
| global | (prototype: `--panel` table heads, dashed ghost add-filter) | **Section identity accents** (`--sect-*` tokens: sidebar group dots + head-card top bar via route `meta.section`), **scanner identity dots** (seg-control options + mix-bar labels wear trivy-teal/grype-violet; coral selection language untouched), **table-head band = solid slate** (`--table-head-bg: var(--slate2)` + parchment text, one token app-wide; third ruling on this surface — panel invisible, bg merged, washes faint/busy), **add-filter on card bg + darkened dashes** | 2026-07-16 §8.5 rulings on built specimens: keep-all accents · band B2 of B1/C/B2 |
| 6 | (v4 prototype) narrow finding detail: 8-col per-scanner evidence table, stacked full-width cards, sticky triage rail | **Wide route**; evidence table **transposed** (scanners = columns, attributes = rows); grid rows share tracks — evidence \| docked triage (equal height), decisions \| activity side-by-side, affected components full-width; GridPager always visible on all three tables; slate band on triage + activity heads ONLY; sticky removed; "scanners disagree" written out; unassigned chip | 2026-07-17 §8.5 A/B rulings on built specimens (#434): transposed in · docked over slideover · tracks-or-full-width |
| 3 | (prototype pills: include-only, "is / is one of") | **NOT-pill** (issue 349): a negated filter renders the fill/outline duality — hollow body (transparent on the canvas, 1.5px border, no shadow) with ONLY the op words ("is not"/"is none of") in red (`--fpill-not-op`) + bold; the op word doubles as the include⇄exclude toggle; picker gets an is/is-not seg. Red-tint fill specimen (B) built and LOST | 2026-07-17 §8.5 A/B ruling on built specimens: outline wins, keep the red op words only |
| 6 | §6 card counts "from `/findings/facets`" | Held EXACTLY as written — a `/findings`-based count was built first and immediately leaked a PIT per card + 429'd the concurrency cap; count = severity-bucket sum from facets | 2026-07-17, M9f slice 4 (the spec was right) |
| 6 | — | Cards additionally show the schema-v2 **workbench capture** (columns/density/sort/relative window; cluster-agnostic by shape) and page through the kit GridPager (operator ask); apply = deep-link round-trip incl. `!`-negation grammar | 2026-07-17, M9f slice 4 |
| global | (prototype topbar: disabled search input, text sign-out, mixed control heights) | **Topbar register**: all three controls (cluster switcher · time picker · search) at **40px** with **2px `--line` borders**, keep-beige (white-chip and slate-tint A/Bs LOST); search sits on `--bg` with ink hint + real control wash; Sign out = kit UiButton `control`; FilterBar pills/add-filter at **38px** | 2026-07-17 §8.5 rulings on built specimens (M9f slice 2) |
| global | (prototype primary button: gloss — inset highlight + drop shadow) | **Flat solid coral** (solid-button grammar): hue kept, gloss removed; hover/active = `--coral-dd` (a full step — `--coral-d` was too small). Muted-terracotta and soft-wash variants built and LOST | 2026-07-17 §8.5 ruling (M9f slice 3) |
| global | (prototype drawer: flush right panel, opaque card) | **Glass floating drawer** (SlideoverShell): `--glass` 0.78 white + 14px backdrop blur, neutral `--glass-edge`, 12px scrim detach + 4px scrim blur, nested head radius (kills the corner seam). 0.65 opacity tried and reverted | 2026-07-17 §8.5 rulings (M9f slice 3) |
| global | (prototype: topbar search input) | **⌘K command palette** (issue-319 ruling): composed `/findings/groups` queries (CVE/image/namespace) + jump-to-screen off the ONE nav model; the topbar "input" is a button that opens it | 2026-07-17, M9f slice 2 |
| global | — | **Notification bell**: ringed count badge (server unread, pauses on failed poll), inbox rows with per-row ✕ + Mark-all-read/Clear-all (kit mini buttons), ready-export resolves the signed token on click (expired flips the row), toast ECHO for mid-session arrivals only | 2026-07-17 rulings (M9f slice 3) |
