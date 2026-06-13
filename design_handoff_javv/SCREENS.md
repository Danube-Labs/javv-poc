# Screens — javv

Per-screen spec: purpose, layout, components, copy, interactions. Cross-reference the live behavior
in `standalone/JAVV Prototype (standalone).html`. Source file noted per screen. All screens share
the **shell** (sidebar + topbar) from `app/main.jsx` and the **filtering module** from
`app/filters.jsx` where they have a facet rail / filter bar.

Common layout: `.screen` (max-width 1380px, centered). `.screen-head` = `h1` + subtitle on the left,
actions on the right. Screens with filtering use `.findings-layout` = `[facet rail | main]` grid that
stacks below ~1120px.

---

## Shell (`app/main.jsx`)

**Sidebar** (226px, slate `#16232F`): brand lockup (click → All clusters); grouped nav (Monitor /
Inventory / Audit / Insights / Configure) — active item gets coral left-border + tinted bg; footer
shows sweep-health chip (links to Scanner status) + version line `v1 · schema 3 · MVP`.

**Topbar** (56px, white): cluster switcher (left) · time-range picker + global search (center) ·
notification bell + avatar (right).
- **Cluster switcher** — dropdown listing clusters by `cluster_id`; switching re-scopes the app.
- **Time-range picker** — Kibana-style: **Quick** (last N minutes/hours/days/weeks), **Interval**
  (from–to), **Single day**. Selection re-scopes every time-series and the Contributors page.
- **Global search** — ≥2 chars searches CVEs → finding, images → image detail, packages → filtered
  Findings; grouped result dropdown; click jumps to the result.
- **Bell** — badge count; dropdown of *your* notifications: SLA-overdue-assigned-to-you (red icon)
  and newly-assigned findings (blue icon); each clicks through to the finding.

---

## 1. All clusters (`screens-clusters.jsx`) — fleet rollup
**Purpose:** fleet landing page; one row per cluster.
**Layout:** fleet KPI strip (5 cards: total findings + per-severity) → table of clusters.
**Table columns:** Cluster (name + `cluster_id` mono) · Health chip · Images · Replicas · severity
**MixBar** (labeled counts, consistent with Running images) · Last sweep (RelTime).
**Interactions:** row → that cluster's **Overview**; health chip degraded/down → Scanner status.
Severity mix here must match the Running-images MixBar style exactly (counts visible, not hover-only).

## 2. Overview (`screens-overview.jsx`) — single cluster
**Purpose:** current state of the active cluster.
**Layout:**
- **KPI strip** (4 cards CRITICAL/HIGH/MEDIUM/LOW): big number, +N (30d) delta, sparkline. Cards are
  **click-through** → Findings pre-filtered to that severity. Plus a **Fix-coverage KPI**
  ("% of findings with a fix available") — the most actionable planning number.
- `grid-2-1`: **Vulnerabilities over time** (stacked area, ECharts, faceted by scanner) + legend
  with totals · **Package type** donut + legend.
- `grid-1-1`: **Per namespace** table (rows → Findings filtered by ns) · **Top components** table.
- `grid-1-1`: **Newly published** bar chart · **Language-specific binaries** table.
- Header actions: Export CSV · **Triage critical** (→ Findings filtered CRITICAL).
- A **scanner-type filter** applies here (both overviews can filter by scanner).
Subtitle: "Current state across **<cluster>** · N workloads · last sweep <RelTime>".

## 3. Findings (`screens-findings.jsx`) — the core grid
**Purpose:** triage queue; the densest, most-used screen.
**Layout:** `.findings-layout` = **facet rail** (left) + **main**.
- **Facet rail** (`FacetRail`): search box header + facet groups Severity, Scanner, Attributes
  (KEV / Fix available / Scanners disagree), State, Assignee (incl. "Unassigned"), Namespace,
  Package type — each with live server-side counts.
- **Toolbar row:** `FilterBar` (Kibana "+ Add filter" → pills) + **Save view** button (appears when
  filters active) + `ColumnsMenu` (show/hide columns, Compact/Comfortable).
- **Server note:** "All sort / filter / facet counts computed server-side via OpenSearch aggregations".
- **Bulk bar** (appears when rows checked, dark slate): "N selected" + Acknowledge / Assign… /
  Export selected / Clear selection.
- **Table** columns (checkbox · Vulnerability · Severity · EPSS · KEV · Component · Package ·
  **Current** · **Fixed** · Scanner · SLA · State · Assignee). Current/Fixed are **two columns**.
  Sortable: Vulnerability, Severity, EPSS, SLA, State, Assignee. EPSS only renders where the
  scanner provides it (Grype). Scanner cell shows a `±` **disagreement** badge when `disagree` set,
  tooltip "Trivy: CRITICAL · Grype: HIGH".
- **Pager** (Pager component, 10/25/50).
- **Empty / first-run state:** before the first sweep lands, show a friendly empty state (not a
  blank grid) explaining the sweep hasn't run yet.
- Row → Finding detail. Header action: Saved views · Export CSV.
Accepts a `preset` (`{ filters, q }`) from deep-links and saved views to pre-seed `useFilters`.

## 4. Finding detail + triage (`screens-finding-detail.jsx`)
**Purpose:** full context + the triage action — the differentiator.
**Layout:** back-link → header (CVE mono `h1`, severity solid tag, KEV tag, title, meta: CVSS · EPSS
· CWE · published · discovered) + **SLA box** (right; red when overdue). Then `grid-2-1`:
- **Left stack:** Description card (prose + CVSS vector + reference links) · **Per-scanner evidence**
  table (Trivy AND Grype rows: severity, source, fixed-in, match status, vuln-DB date — "no black
  box, no merge") · Affected components table (rows → image detail).
- **Right: Triage panel** (sticky): Assigned-to (avatar + **Assign to me** / Reassign) · **State**
  picker (Open / Acknowledge / Resolve) with the "staleness is automatic, resolve is manual" hint ·
  **Justification** / **Impact** / **Action** textareas · **Approver** + **Task** fields ·
  **Save to audit trail** · link to Approval list.
Gate the write actions on RBAC (Operator+ to resolve/assign; Security Lead+ to approve).

## 5. Saved views (`screens-views.jsx`)
**Purpose:** the Kibana-"dashboards" equivalent — named filter sets over Findings.
**Layout:** responsive card grid (`minmax(290px,1fr)`). Each card: bookmark icon + name + live count;
description; filter pills; footer owner + "Open". Card → Findings pre-filtered (passes `filters` as
preset). Header action: **New view** (→ Findings to build one; "Save view" lives there).

## 6. Running images (`screens-images.jsx` → `Images`)
**Purpose:** k8s-runtime inventory.
**Layout:** `.findings-layout` — facet rail (Severity / Scanner / Namespace / Application) + filter
bar + table + pager (10/25/50). Has the **same filter affordances as Findings** (this parity was an
explicit requirement). A **Fix-available filter** option is present.
**Columns:** Image (name + registry mono) · Tag · Namespace · **Replicas** (header note "last
sweep") · Vulns total · **Severity mix** (labeled MixBar — counts visible, not hover-only) · Scanners
· Last seen (RelTime). Row → Image detail.
Subtitle clarifies replicas are observed at last sweep, not live. No live "running/stopped" flag.

## 7. Image detail (`screens-images.jsx` → `ImageDetail`)
**Purpose:** one image, per-scanner.
**Layout:** back-link → header (cube glyph, name + tag badge, full ref, meta: replicas at last sweep,
ns, app, last-seen RelTime) + **scanner dropdown** ("Showing results from <Trivy|Grype>") — switching
swaps the per-scanner view. Then severity-summary cards (C/H/M/L + total for the chosen scanner) +
findings table (Current/Fixed as two columns) scoped to that scanner. Row → finding detail.

## 8. Approval list (`screens-approvals.jsx`)
**Purpose:** exceptions ledger.
**Layout:** filter bar (Severity / Status / Approver) + table + pager. Columns: Vulnerability ·
Severity · Status · Justification · Impact · Action · Approver · Task · When (RelTime). Row → finding.

## 9. Audit log (`screens-audit.jsx`)
**Purpose:** immutable "who did what" stream. Built entirely on the shared filter module (proof of reuse).
**Layout:** facet rail (Action, User) + filter bar + table + pager. Columns: When (RelTime) · User
(avatar+name) · **Action** tag · Target · Detail · **Task**. Finding-targeted rows click through;
system/config rows don't. Task shows `TASK-####` or em-dash.

## 10. Contributors (`screens-heroes.jsx`)
**Purpose:** leaderboard — who's clearing the backlog.
**Layout:** team KPI strip (resolved / acknowledged / median TTR / SLA-met % / criticals cleared) →
**top-3 podium** (rank, avatar, name, role, resolved count, severity mix, SLA%, median, streak —
streak uses a dot indicator, **no emoji**) → full **leaderboard** table (avatar, resolved,
acknowledged, severity mix, median, SLA%, pace sparkline) → **Resolved over time** stacked bar
(ECharts) → **Recent activity** feed. **Must be scoped by the global time-range picker** — the
"last 30 days" label is driven by the picker, not hardcoded. Names use Central/Eastern-European
placeholders; severity colors stay firewalled from brand coral.

## 11. Scanner status (`screens-scanner-status.jsx`)
**Purpose:** per-scanner ingest health + degraded/error home.
**Layout:** per-scanner status cards (Trivy / Grype: version, health chip, last run, ingested 24h,
failed 24h, queue depth, DB age) → **Ingested vs failed over time** line chart (ECharts, Kibana-style
lens, mirrors "Vulnerabilities over time") → **Failed ingests** table: When · Scanner · Image · Stage
(pull/scan/parse/push) · Error · Retries · Status (retrying / dead-letter / resolved). Shows the
backoff+retry / dead-letter / idempotent-ingest model.

## 12. Settings (`screens-config.jsx`)
**Purpose:** all configuration. Left sub-nav + panel + **sticky save bar** per section (Discard /
Save; flips on edit).
Sections:
- **Scan scope** — Running-only toggle; **Include list** (active toggle + namespace text list) and
  **Ignore list** (active toggle + namespace text list) — symmetric, simple (not a mode switch);
  excluded image globs; skipped workload kinds.
- **Scanners** — per-scanner cards (enable, **version select**, Trivy: severities / ignore-unfixed /
  pkg-types / layer scope / timeout / concurrency; Grype: fail-on / only-fixed / scope / app-update).
  Banner: results kept per-scanner, never merged.
- **Schedule** — scan interval, daily sweep time, staleness window, retry+backoff.
- **SLA policy** — editable SLA days per severity + KEV override hours (Security Lead+).
- **Ignore rules** — allowlist table (id, scope, reason, added-by, expires) — reason + expiry required;
  expired rules resurface.
- **Vulnerability DB** — **two sub-tabs (Trivy DB / Grype DB)** under one section, reflecting their
  different distribution models (Trivy OCI `--db-repository` + java-db + refresh + skip-update;
  Grype `listing.json` URL + CA cert + auto-update + max-built-age + validate-age) + shared cache note.
- **Access & registries** — HTTPS-only banner (TLS-only, immutable); **push-token table** (one scoped
  `push:findings` token per scanner; rotate/revoke; add token); auto-resolve imagePullSecrets;
  known registries.
- **Users / RBAC** — users table (avatar, role, last active) + the permission matrix.
- **Cluster** — `cluster_id` (immutable) + editable `cluster_name`.

---

## Cross-cutting behaviors to preserve
- **Deep-links:** Overview KPI/severity cards & namespace rows, All-clusters rows, saved views, and
  search results all pass a `preset` into the target screen's `useFilters`. Namespace drill from
  All clusters carries cluster context two levels deep.
- **RelTime everywhere:** relative label + absolute in tooltip. Deadlines stay absolute.
- **Keyboard + focus:** Esc closes dropdowns; ↑/↓ navigate filter menus; visible coral focus rings.
- **First-run / empty states** on data screens.
- **RBAC gating** on every mutating affordance.
