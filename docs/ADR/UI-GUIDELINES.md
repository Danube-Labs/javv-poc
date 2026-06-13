# JAVV — UI Guidelines (v1)

> **v1, derived from the inspiration screenshot** `javv/[k8s] Container Vulnerabilities.png` (a
> Kibana / OpenSearch-Dashboards "[k8s] Container Vulnerabilities" board). This is the **target** for
> the polished dashboard — *not* the barebones first-flow (see `PLAN.md` §6). Will evolve.

## North star
A **dense, single-page, light-themed analytics dashboard** in the Kibana mold: lots of data visible at a
glance, everything filterable, one-click CSV from any panel. Density over whitespace.

## Page structure (top → bottom, as in the inspiration)
1. **KPI header row** — large metric tiles:
   - Severity counts: **Critical / High / Medium / Low** (the screenshot shows ~`85 / 554 / 117 / 10`).
   - Totals: images, total findings, fixed/with-fix, distinct CVEs (e.g. `467 / 4,396 / 1,703 / 119`).
   - Big number, small caption. Severity tiles tinted with the severity palette below.
2. **Distribution row** — a **categorical donut** (findings by namespace / package-type) beside a
   **ranked table** (top-N images or namespaces by finding count).
3. **Trend row** — **time-series area/line** charts (findings over time, split by severity) plus
   secondary **teal bar charts** (per-period counts / top-N).
4. **Findings table** — the workhorse: dense, sortable, paginated; **severity-colored cells**. Columns:
   Vuln/CVE ID · package/component · installed version · fixed version · severity · image · namespace/workload.
5. **Image inventory table** — image name · tag · digest · finding counts.
6. **Audit/detail table** (bottom) — CVE title/description · status · audited_by/approver · timestamps.

## Severity palette (data only — never brand chrome)
| Level | Use | `Suggestion:` hex |
|---|---|---|
| Critical | darkest red | `#8B0000` |
| High | red/orange | `#D7263D` |
| Medium | amber | `#F18F01` |
| Low | yellow | `#F4D35E` |
| Negligible / Unknown | neutral gray | `#9CA3AF` |

Apply as a left cell tint / `Tag` chip in tables and as the fill on severity charts. Keep the donut's
categorical colors distinct from the severity scale to avoid confusion.

## Theme & chrome
- **Light theme**, neutral gray surfaces, slate text. Subtle panel borders/cards.
- **Accent:** teal/cyan (`Suggestion: #2EC4B6`) for bars, links, primary actions — aligns with brand (`PLAN.md` §1).
- Compact spacing, small-but-legible type, numerals tabular-aligned in tables.

## Interaction principles
- **Global filter bar:** namespace, image, team/app/org tag, severity, timestamp — every panel reacts.
- **Scanner facet is mandatory:** because findings are per-scanner, a **Trivy / Grype** selector governs
  the page; aggregations must never sum across scanners (would double-count — `PLAN.md` §3).
- **One-click CSV** from any table/lens (Kibana-style). Exports must be injection-sanitized (`PLAN.md` §7).
- **Per-image report:** drill into an image → its findings, with the scanner dropdown
  ("nginx — Trivy" / "nginx — Grype").
- Sortable, paginated, server-driven tables (data volume lives in OpenSearch).

## Component mapping (tech)
- **PrimeVue:** `DataTable` (findings/inventory/audit), `Card` (KPI tiles + panels), `Tag`/`Chip`
  (severity), `Dropdown` (scanner + filters), `Toolbar` (filter bar).
- **vue-echarts:** `pie` (donut), `line`/area (trends), `bar` (teal count charts).

## Out of scope for now
Dashboard *builder*, custom color theming, dark mode — deferred per `PLAN.md`. Build the curated layout
above, not a configurable canvas.
