# Screens — javv (v5, refreshed against the shipped backend)

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
- **DECIDE** flags are open operator rulings — the recommended option is drawn on the screen and
  visibly badged "DECIDE".
- **BLOCKED: needs backend** marks data no shipped endpoint provides. §D of the drift table is the
  only sanctioned additions list; anything else blocked is called out as *not yet planned*.

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
- Cluster list: no endpoint enumerates clusters. **DECIDE (D-5/C-5)** — recommended (drawn):
  a small `system-config` cluster-registry doc providing `cluster_id` + relabelable
  `cluster_name`; fallback if declined: MVP shows raw `cluster_id`s from deploy config.
  Until decided/built: **BLOCKED: needs backend** (cluster enumeration + display names).
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
- Cluster name source flagged DECIDE (D-5).
- "Replicas" column: no inventory read endpoint is shipped — **BLOCKED: needs backend** (see
  Running images); column shows the blocked note or is dropped until the inventory read exists.

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
- **Package-type donut — DECIDE (B-1)**, recommended (drawn): **cut for MVP**, layout slot kept
  with a subtle "post-MVP" placeholder; alternative is a schema-v4 envelope change (lockstep
  deploy, not recommended).
- **Top components** + **Language-specific binaries** tables — **cut** (B-6, no backing agg);
  layout slots left.
- **Newly published** bar chart — **cut** (B-2: no `published` field exists); slot reused by the
  scan-activity trend.

**States:** loading (skeletons per card); empty/first-run ("no sweep has landed yet"); degraded;
scanner-silent banner; `T<now` history banner (single-cluster rewind is fully supported once M8b
lands; 501-state before that, C-1).

**Changed vs SCREENS.md:** A-1 (lowercase + negligible), B-1/B-2/B-6 (widget cuts), A-m9
(trend semantics label), C-1 (time-travel states). Scanner-type filter stays (it maps to the
`scanner` filter param).

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
risk_accepted, resolved, stale) · Assignee (incl. Unassigned) · Namespace.
**Removed:** Package type facet (B-1 cut).
> **DECIDE (A-1), drawn on the rail:** show `negligible` as its own muted bucket (recommended —
> Grype emits it; hiding it breaks "counts sum") vs folding into `unknown`.

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
cut), B-3 (raw EPSS only), B-4 (images count = agg), B-5 (SLA server-computed), A-m1 (cursor
error states), C-2 (export entry point → Export dialog, below).

---

## 4. Finding detail + triage (bolt: **M9b**)

Layout preserved: back-link → header → `grid-2-1` (evidence stack left, sticky triage panel
right).

**Data**
- The finding row (all real fields, see DATA_MODEL-v5) from `GET /api/v1/findings?cluster_id=…&cve_id=…&image=…` —
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

**Changed vs SCREENS.md:** C-2 (TTL/expiry affordances + 410 state — new), A-6 (export is
session-only: available to every authenticated user; the v4 "Viewer cannot export" matrix row is
dropped. **DECIDE**, drawn as available-to-all: add a `can_export` capability? — backend change,
not recommended for MVP).

---

## 6. Saved views (bolt: **M9f**)

Card grid preserved.

> **DECIDE (C-6), drawn on screen:** **localStorage-only for MVP (recommended)** — cards carry a
> "stored in this browser" hint; alternative is a new `system-views` index ([BE]: INDEX-MAP +
> MAPPING_VERSION + bootstrap + tests). No shipped endpoint exists — server-side views are
> **BLOCKED: needs backend** if chosen.

**Data:** view definitions from localStorage; the per-card **live count** is
`GET /api/v1/findings/facets?<view's filter params>` (server agg — fetched lazily per visible
card; never counted client-side). Card → Findings with the filter preset (deep-link round-trip
must reproduce identical query params).

**States:** empty ("save a filter set from Findings"); count-loading per card; degraded (counts
show em-dash).

**Changed vs SCREENS.md:** C-6 (persistence DECIDE + storage hint); owner column dropped in the
localStorage variant (there is no server-side owner).

---

## 7. Running images (bolt: **M9c**)

**Data**
- Per-image severity mix + finding counts: `GET /api/v1/findings/groups?cluster_id=…&group_by=image&…`
  — per-scanner counts side-by-side + the `trivy_count`/`grype_count`/`count_delta`
  count-disagreement pair (D5b; per-image, distinct from per-finding `disagree` — V4-DELTA
  conflict 7). Facets for the rail via `GET /api/v1/findings/facets`.
- Inventory metadata (replicas at last sweep, app, first/last seen): **BLOCKED: needs backend** —
  no session read over `javv-images`/inventory runs is shipped; the M8b point-in-time query API
  is the planned reader (check at M9c kickoff whether it covers `T=now` inventory or a small read
  is needed; *not* in drift-table §D — flag to the operator).
- Image naming: compose from `image_repo` + `tag` (no `image_ref` field exists — M9c update,
  #156-3).

**Columns:** Image (`image_repo` + registry mono) · Tag · Namespace · Replicas (blocked note
until the inventory read lands) · per-scanner finding counts (`T n / G n / Δ` — never a merged
total) · Severity mix (labeled MixBar, per scanner) · Scanners · Last seen.

**States:** loading; empty/first-run; **scanner-silent** banner ("Inventory as of T; scanner
silent since…"); **last-run-incomplete** banner ("showing the last complete inventory"); `T<now`
history banner; degraded. Never shows partial/stale inventory as live (V4-DELTA).

**Changed vs SCREENS.md:** A-3/D5b (count-disagreement pair per image), B-1 (ptype facet cut),
#156-3 (repo+tag composition), inventory read flagged BLOCKED.

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

**Data:** **BLOCKED: needs backend** — no session read over `system-audit-log` is shipped and
none is in drift-table §D. The M9d README anticipates `GET /audit` "if not already in M5d" —
flag to the operator that this read must land before M9d. (Spec drawn against the D32 doc shape.)

**Layout:** facet rail (entity_type, action, actor) + filter bar + timeline table: When · Actor ·
entity_type+action tag pair · Target (frozen `target_ids`, rendered verbatim — never a
re-evaluated selector) · Detail. **Click-through only where `entity_type=="finding"`** (A-5).
Task column dropped (no field; Jira linkage is v1.1 — V4-DELTA-1).

**States:** loading; empty; degraded; retention note ("audit window bounded by
`system-audit-log` retention").

**Changed vs SCREENS.md:** A-5 (structured entity_type+action replaces the 8-string enum;
click-through rule; Task column dropped); endpoint BLOCKED.

---

## 11. Contributors (bolt: **M9d**)

**Data:** `GET /api/v1/contributors?cluster_id=…&range=…` (FR-15, shipped) — leaderboard +
TTR/SLA-hit computed server-side from `system-audit-log`. Scoped by the global trend window; the
"last 30 days" label follows the picker; window clamps to audit-log retention.

**Semantics label (A-m9):** any resolved-count series driven by trends carries
`resolved_semantics: "scan_resolved"` — label "scan-observed resolutions", distinct from human
`state=resolved` triage counts from the audit log. Don't conflate the two on one chart.

**Layout preserved:** team KPI strip → podium → leaderboard → resolved-over-time
(`GET /api/v1/trends/findings`, labeled per A-m9) → activity feed (from the audit read — same
BLOCKED note as screen 10 for the feed only).

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
  **BLOCKED: needs backend** — no session read of latest scan-event provenance is shipped (not
  in §D; flag — M9e's ScanningView has the same need, one small read serves both).
- **Last-N scan runs** (counts, durations): same blocked read.

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
**No version picker anywhere. No editable schedule/tuning.** Same blocked provenance read as
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
> **DECIDE (A-4), drawn with 4 roles:** seed a 5th role? Backend supports adding one; default —
> keep 4 (recommended).

### 13.7 Data & OpenSearch — editable (Admin)
Per-cluster retention days, rollover knobs, snapshot repo/schedule + manual snapshot/restore —
retention/rollover offered **only** for time-partitioned append families; the mutable family
(findings, watermarks, scan-orders, system-*) never gets a drop control.
**Data:** `PUT /settings/retention`, `PUT /settings/rollover`, `POST /snapshots`,
`POST /snapshots/{id}/restore` — **M9e deliverables, planned, BLOCKED until they land**; gated
`can_manage_retention` / `can_restore_snapshot` / `can_drop_index`, journaled.

### 13.8 Cluster
`cluster_id` immutable (mono). `cluster_name` editable **iff** D-5 decides the registry doc
(DECIDE badge, same as screen 1).

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

## DECIDE register (all drawn on-screen, recommended option shown)

| Id | Where | Recommendation drawn |
|---|---|---|
| A-1 | Findings rail, Overview KPIs | Show `negligible` as its own muted bucket |
| A-4 | Settings → Users & roles | Keep 4 seeded roles |
| A-6 | Export dialog | Export stays session-only; no `can_export` capability |
| B-1 | Overview donut slot | Cut package-type donut for MVP |
| C-6 | Saved views | localStorage-only for MVP |
| D-5/C-5 | All clusters, Settings → Cluster | Small `system-config` cluster registry for `cluster_name` |

## BLOCKED register (needs backend; §D-planned items marked)

| Screen | Needs | Status |
|---|---|---|
| Export schedule download, Bell | `GET /api/v1/reports/{id}/download` · `GET /api/v1/notifications` + mark-read | **Planned** (M7 slice 3 / D-3) |
| Settings → Scan scope | Session read of the scan-scope doc | **Planned** (D-2) |
| All clusters, Settings → Cluster | Cluster registry / display names | **Planned decision** (D-5) |
| Audit log, Contributors activity feed | Session read over `system-audit-log` | **Not in §D — flag** (M9d README anticipates it) |
| Scanner status, Settings → Scanning provenance | Session read of latest scan-event (provenance + effective_config + last-N runs) | **Not in §D — flag** (one small read serves both screens) |
| Running images inventory metadata | Session read over image/inventory runs (replicas, seen) | **Not in §D — flag**; check M8b coverage at M9c kickoff |
| Image detail point-in-time | M8b point-in-time query API | **Planned** (M8b milestone) |
