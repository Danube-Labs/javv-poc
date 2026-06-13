# Handoff: javv — *just another vulnerability viewer*

> **javv** by **Danube Labs** — a Kubernetes-runtime container vulnerability viewer.
> A purpose-built UI over Trivy + Grype scan results, served from OpenSearch.
> **Not** embedded OpenSearch Dashboards / Kibana — a real product around the same data.

---

## 1. Read this first

This bundle is a **design reference**, not production code. Everything in `prototype/` is an
**HTML + React-via-Babel-CDN prototype** that demonstrates the intended look, layout, copy, and
interaction model. It is deliberately a single-page, client-rendered mock with a **fabricated
in-memory dataset** (`app/data.js`) so reviewers can click through every screen offline.

Your job is to **recreate these screens in the real target stack** using its established patterns —
**not** to ship this HTML. The agreed production stack (from the brief) is:

| Layer | Choice |
|---|---|
| Framework | **Vue 3** |
| UI / chrome | **PrimeVue** |
| Charts | **vue-echarts** (Apache ECharts) |
| Data | **OpenSearch** — all pagination, sort, filter, facet, KPI counts done **server-side via OpenSearch aggregations**. Never ship raw findings to the client to compute counts. |
| Dense-grid table engine | **Deferred** (see `UI-tools.md` in the product repo) — decide before M5. The prototype uses plain HTML tables; column-visibility + density toggle are built in as a probe for this decision. |

The prototype is written in **React** only because that's the prototyping tool's native mode.
Treat the JSX as **executable spec**, not code to port line-by-line. Component boundaries,
state shape, and the filter module (below) map cleanly onto Vue components + a composable.

### Fidelity: **High**
Final colors, typography, spacing, severity semantics, copy, and interactions are all intended as
shown. Recreate pixel-faithfully using PrimeVue + the design tokens in `DESIGN_SYSTEM.md`.
Where PrimeVue's default component diverges visually, theme it to match these tokens rather than
accepting the stock look.

---

## 2. What this product is

A security engineer / platform owner / security lead logs in to see **what vulnerabilities are
actually running in their Kubernetes clusters** — derived from the live k8s API (what's deployed),
not a registry crawl. Two scanners (Trivy and Grype) push results independently; **javv keeps them
per-scanner and never merges them** — that transparency is a core product pillar (it surfaces
scanner disagreement instead of hiding it).

Core loops:
1. **Monitor** — fleet & per-cluster overviews, KPI trends.
2. **Triage** — filter the findings grid, open a finding, set state + justification, assign an owner.
3. **Audit** — every action is logged; exceptions (ignore rules / acknowledgements) carry a
   justification, approver, and expiry.
4. **Configure** — scan scope, scanners, schedule, SLA policy, vuln-DB sources, access tokens, users.

See **`SCREENS.md`** for a screen-by-screen spec, **`DATA_MODEL.md`** for entity shapes,
**`DESIGN_SYSTEM.md`** for tokens/components, **`ARCHITECTURE.md`** for the suggested Vue mapping
and the OpenSearch query contract, and **`DOMAIN_GLOSSARY.md`** for the security terms.

---

## 3. Information architecture (sidebar)

```
javv · by Danube Labs
─ MONITOR
   • All clusters        fleet rollup, one row per cluster   → clusterId deep-link
   • Overview            single active cluster, KPIs + charts
   • Findings            the dense vuln grid (facets + filter bar + bulk)
   • Saved views         named filter sets (Kibana-dashboards equivalent)
─ INVENTORY
   • Running images      k8s-runtime image inventory
─ AUDIT
   • Approval list       exceptions w/ justification + approver
   • Audit log           who did what, when (immutable event stream)
─ INSIGHTS
   • Contributors        leaderboard: who's clearing the backlog
─ CONFIGURE
   • Scanner status      per-scanner ingest health, failed files
   • Settings            scan scope · scanners · schedule · SLA · ignore rules · vuln DB · access · users/RBAC · cluster
```

Top bar (persistent): **cluster switcher** (keyed on `cluster_id`), **global time-range picker**
(quick relative / interval / single-day, Kibana-style), **global search** (CVE / image / package
→ jumps to result), **notification bell** (your SLA breaches + new assignments), **user avatar**.

---

## 4. The 12 screens (detail in SCREENS.md)

| # | Screen | Route key | File |
|---|---|---|---|
| 1 | All clusters | `clusters` | `app/screens-clusters.jsx` |
| 2 | Overview | `overview` | `app/screens-overview.jsx` |
| 3 | Findings | `findings` | `app/screens-findings.jsx` |
| 4 | Finding detail + triage | `finding` | `app/screens-finding-detail.jsx` |
| 5 | Saved views | `views` | `app/screens-views.jsx` |
| 6 | Running images | `images` | `app/screens-images.jsx` |
| 7 | Image detail (scanner dropdown) | `image` | `app/screens-images.jsx` |
| 8 | Approval list | `approvals` | `app/screens-approvals.jsx` |
| 9 | Audit log | `audit` | `app/screens-audit.jsx` |
| 10 | Contributors | `heroes` | `app/screens-heroes.jsx` |
| 11 | Scanner status | `scanner` | `app/screens-scanner-status.jsx` |
| 12 | Settings | `settings` | `app/screens-config.jsx` |

Shared building blocks: `app/components.jsx` (chips, KPI cards, charts wrapper, avatar, pager,
relative-time), `app/filters.jsx` (the reusable filtering module — **read this; it's the most
important shared piece**), `app/main.jsx` (shell, router, topbar, search, bell).

---

## 5. How to run the prototype

- `prototype/JAVV Prototype.html` — open in a browser. Loads React/Babel/ECharts from CDN, so it
  needs network on first load. Source is split across `app/*.jsx` for readability.
- `standalone/JAVV Prototype (standalone).html` — everything inlined; **works fully offline**.
  Use this for stakeholder review. Do not edit it — it's compiled output.

There is **no build step** and **no backend** — `app/data.js` fabricates a deterministic dataset on
`window.JAVV`. In production every one of those arrays becomes an OpenSearch-backed API call.

---

## 6. Critical product rules (do not lose these)

1. **Per-scanner, never merged.** A CVE seen by both Trivy and Grype is two rows of evidence, not
   one averaged row. Facets/counts are faceted by scanner. The **scanner-disagreement** flag exists
   precisely to make divergence visible.
2. **Server-side everything.** Counts, facets, sort, pagination = OpenSearch aggregations. The client
   never holds the full findings set to compute a number.
3. **Severity colors are data, not brand.** Red/orange/yellow/blue are reserved for
   CRITICAL/HIGH/MEDIUM/LOW. The brand coral (`#EC7E54`) is **never** used to mean severity.
4. **Runtime, not registry.** Inventory = what the k8s API says is deployed. "Replicas" = observed
   at the last sweep (javv does **not** continuously watch pods — there is no live "running" flag).
5. **Staleness is automatic, resolve is manual.** Findings not re-pushed within the staleness window
   flip to `stale` on the daily sweep. `resolved` is only ever set by a person.
6. **Exceptions are accountable.** Ignore rules and acknowledgements require a justification and an
   expiry; expired rules resurface automatically. Everything lands in the audit log.
7. **RBAC gates actions.** Viewer < Auditor < Operator < Security Lead < Admin (matrix in
   `DATA_MODEL.md`). e.g. a Viewer sees dashboards only; Auditor adds read of audit log + export;
   Operator can acknowledge/assign/resolve; Security Lead approves exceptions & edits SLA; Admin
   manages scanners, users, tokens.
8. **Scanners authenticate with an HTTPS API token only.** Any scanner type that holds a scoped
   `push:findings` token can push over TLS — nothing else is required or accepted.

---

## 7. Files in this bundle

```
design_handoff_javv/
├── README.md                ← you are here
├── SCREENS.md               per-screen layout, components, copy, interactions
├── DATA_MODEL.md            every entity shape + RBAC matrix + enums
├── DESIGN_SYSTEM.md         color/type/spacing tokens, component inventory, CSS class map
├── ARCHITECTURE.md          Vue/PrimeVue/ECharts mapping, OpenSearch query contract, routing, state
├── DOMAIN_GLOSSARY.md       CVE, EPSS, KEV, CVSS, SBOM, Trivy/Grype, SLA, staleness…
├── prototype/               editable source (HTML + app/*.jsx + branding)
│   ├── JAVV Prototype.html
│   ├── app/*.jsx, data.js
│   └── branding/favicon.svg
├── standalone/              offline single-file build for review
│   └── JAVV Prototype (standalone).html
└── brand/                   approved brand assets + guide
    ├── BRAND.md
    ├── icon.svg  lockup.svg  wordmark.svg
```

---

## 8. Suggested build order

1. **Shell + routing + design tokens** (sidebar, topbar, cluster switcher, theme PrimeVue).
2. **Filtering module** (`useFilters` composable + `FacetRail` / `FilterBar` / `ColumnsMenu`
   components) — Findings, Running images, Approvals, and Audit log all depend on it.
3. **Findings grid + Finding detail/triage** — the core loop; wire to OpenSearch aggregations.
4. **Overview + All clusters** (vue-echarts) and **Running images / Image detail**.
5. **Audit, Approvals, Contributors, Scanner status** (reuse the table + filter shells).
6. **Settings** (scope, scanners, schedule, SLA, ignore rules, vuln DB, access, RBAC users).
7. **Cross-cutting**: global search, notifications, saved views, first-run/empty states, RBAC gating.

Items the team explicitly deferred to the dev phase: real URL routing & shareable view links,
finding↔image two-way cross-nav completeness, and actual CSV export generation.
