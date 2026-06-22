# Architecture — javv (prototype → production)

How the React-via-CDN prototype maps onto the agreed **Vue 3 + PrimeVue + vue-echarts + OpenSearch**
stack. The prototype is client-only with a fabricated dataset; production moves all data + counting
server-side.

---

## 1. Prototype structure (what you're reading)

```
JAVV Prototype.html      shell: fonts, full CSS (:root tokens + all classes), CDN scripts, mount
app/data.js              window.JAVV — fabricated deterministic dataset (→ becomes the API layer)
app/components.jsx        shared presentational components (chips, cards, Chart, Avatar, Pager, RelTime, Icon)
app/filters.jsx           useFilters + FacetRail + FilterBar + ColumnsMenu  ← the reusable filter module
app/main.jsx              App shell, hash-less in-memory router (route = {name, data}), sidebar, topbar, search, bell
app/screens-*.jsx         one file per screen
```

Cross-file sharing is via `Object.assign(window, {...})` at the bottom of each file (a prototype
hack because each `<script type="text/babel">` is isolated). **In Vue this becomes normal ES module
imports** — drop the window globals entirely.

Routing in the prototype is a `useState({name, data})` switch in `App`; `go(name, data)` navigates
and `data` carries the `preset` for deep-links. Replace with **Vue Router** (one route per screen;
`data`/`preset` becomes route params + query).

---

## 2. Suggested production mapping

| Prototype | Vue 3 production |
|---|---|
| `App` switch router | **Vue Router** routes; layout component for shell |
| `Sidebar`, `Topbar`, `ClusterSwitcher`, `GlobalSearch`, `Bell` | Layout + header components; cluster/time-range/user in a **Pinia** store |
| `useFilters(fields, preset)` | **composable** `useFilters(fields, preset)` returning reactive `sel` + actions |
| `FacetRail` / `FilterBar` / `ColumnsMenu` | dumb components driven by the `fields` config + a `countVal` async fn |
| `Card`, `Sev`, `StateTag`, `ScannerTag`, `Kev`, `Sla` | PrimeVue `Card`/`Tag`/`Chip`, themed to tokens |
| `Chart` (ECharts SVG wrapper) | **vue-echarts** `<v-chart :option=… autoresize />` |
| `Pager` | PrimeVue `Paginator` (rowsPerPageOptions [10,25,50]) |
| Findings/Images/Approvals/Audit tables | PrimeVue `DataTable` **lazy mode** (server-side sort/filter/page) — or the deferred dedicated grid engine; see `UI-tools.md`, decide before M5 |
| `Icon` inline set | PrimeIcons or lucide-vue |
| `data.js` arrays | API client → backend → OpenSearch |
| sticky save bar | per-section component bound to a dirty-state ref |

Keep the **`fields` config object** pattern verbatim — it's what guarantees the facet rail and the
filter bar can never diverge. Each screen declares its fields once and passes the same array to both
`FacetRail` and `FilterBar`.

---

## 3. OpenSearch query contract (the important part)

**Never ship raw findings to the client to compute counts.** Every number and page comes from an
aggregation. Concretely:

- **Findings grid** → one `search` with `from`/`size` (pagination), `sort`, and a `bool` filter
  built from the active `sel` (each field = a `terms` filter; multi-select within a field = `should`,
  across fields = `must`). The free-text search box = `multi_match` on cve/pkg/component.
- **Facet counts** (rail + filter-bar menus) → `aggs` with one `terms` (or `filters`) agg per facet
  field, computed **with the other filters applied** (so counts reflect the current narrowing, like
  Kibana). Return `{ field: { value: docCount } }` and feed `countVal(field, value)`.
- **KPIs / severity totals / fix-coverage** → `aggs` (`terms` on severity, `filter` on `fixed!=null`
  for fix-coverage), scoped by cluster + time range.
- **Time series** (Vulns over time, Resolved over time, Ingested/Failed) → `date_histogram` +
  `terms` sub-agg by severity/scanner, bucketed over the global time range.
- **All-clusters rollup** → `terms` on `cluster_id` with severity sub-aggs.
- **Contributors** → `terms` on assignee/actor with metric sub-aggs (count, median TTR via
  `percentiles`, SLA-hit ratio), scoped by the time-range picker.
- **Per-scanner evidence** (finding detail) → query both scanners' docs for the CVE; **render side by
  side, never merge**. The `disagree` flag = the two scanners' severities differ.

Server owns: severity→SLA mapping, staleness transition (daily sweep), KEV/EPSS enrichment, and
RBAC enforcement (the API must re-check permissions; client gating is UX only).

---

## 4. State management (Pinia stores, suggested)

- **session** — current user + role (drives RBAC gating), avatar.
- **cluster** — active `cluster_id`, cluster list.
- **timeRange** — global picker value (quick/interval/single-day) → injected into every query.
- **per-screen filter state** via `useFilters` (local), seeded from route query for deep-links.
- **savedViews** — CRUD of named filter sets (maps to a backend collection; in prototype it's static).
- **notifications** — current user's SLA breaches + assignments (poll or push).

Deep-link contract: `go(screen, { filters, q })` → route with query params; target screen seeds
`useFilters` from them. Saved views and Overview/All-clusters drill-downs use the same path.

---

## 5. Ingest pipeline (context for Scanner status screen)

Scanners (Trivy, Grype) run in-cluster and **push** results to a per-cluster HTTPS endpoint
authenticated by a scoped `push:findings` API token (no other creds). Push is **idempotent** with
**retry + backoff + jitter**; permanent failures go to a **dead-letter** queue (surfaced on Scanner
status). Findings carry `cluster_id` + `schema_version`. Daily **sweep** recomputes staleness.
Vuln DBs refresh on a schedule into a persistent cache (not per-scan) to dodge registry rate limits —
Trivy via OCI artifact, Grype via `listing.json` (see Settings → Vuln DB).

---

## 6. What's intentionally NOT in the prototype (build in production)

- Real auth / SSO / session; server-side RBAC enforcement.
- Real OpenSearch queries (everything is fabricated client-side here).
- URL routing & shareable saved-view links (deferred to dev).
- Actual CSV export generation (buttons are stubs).
- Finding↔image two-way cross-nav completeness (partial in prototype).
- The dedicated dense-grid table engine decision (`UI-tools.md`, before M5).
- WebSocket/polling for live notifications & sweep status.

---

## 7. Gotchas / fidelity notes

- **Severity colors ≠ brand.** Coral/amber are brand; never use them for severity. (Enforced by
  keeping `SEV_COLOR`/`CHART_SEV` separate from brand tokens.)
- **No live pod state.** "Replicas" is last-sweep-observed; don't add a real-time running indicator.
- **Per-scanner is sacred.** Don't dedupe/merge a CVE across scanners anywhere.
- **MixBar consistency.** The labeled severity-mix bar must look identical on All-clusters and
  Running images.
- **RelTime everywhere**, deadlines absolute.
- **EPSS is Grype-provided** — don't show it for Trivy-only rows.
- Fonts: Space Grotesk (UI) + Space Mono (all data/IDs/numbers). Keep mono for CVEs, versions,
  namespaces, image refs, counts, timestamps, tokens.
