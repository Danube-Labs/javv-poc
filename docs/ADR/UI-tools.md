# JAVV — UI Tools Comparison (for your decision)

> Decision aid from the frontend audit (2026-06-09). **Charts are settled** (Apache ECharts via
> `vue-echarts` — best-in-class for our KPI/donut/trend dashboard). **Open decision:** the engine for the
> large, dense **findings / image-inventory / audit** grids. PrimeVue stays for page chrome
> (tiles, filters, dialogs, facets, layout) regardless of which grid engine wins.

## Why this matters
In JAVV the big tables *are* the product (triage happens in them). They must do **server-side
pagination/sort/filter**, **virtualization** for thousands of dense rows, severity-colored cells, and
per-image drilldown — all fast. PrimeVue DataTable can do this but is a reported weak spot at scale
(~15s to render ~2k client-side rows), so it's worth a deliberate choice.

## Comparison

| Criterion | **PrimeVue DataTable** | **AG Grid** | **TanStack Table** |
|---|---|---|---|
| Type | Full component (already in stack) | Full component | **Headless** (you build the UI) |
| Large-dataset performance | Weak client-side; OK only in strict server-side lazy mode | **Excellent** (battle-tested 100k+ rows) | Very good (tens of thousands) |
| Row/column virtualization | Yes (`virtualScrollerOptions`), but lazy+virtual combo is fiddly | **Built-in, robust** | Via a virtualizer (e.g. TanStack Virtual) you wire up |
| Server-side row model | Manual `lazy` mode (you handle page/sort/filter events) | **Built-in server-side row model** (Enterprise) | You implement against your API |
| Built-in CSV/Excel export | Basic CSV | **CSV (free); Excel (Enterprise)** | None — you build it (we export server-side anyway) |
| Filtering/sorting UI | Built-in | Built-in (rich) | You build it |
| Styling control | Themed; moderate | Themeable; opinionated | **Total** (unstyled) |
| Vue support | Native (Vue lib) | Official Vue wrapper | Official Vue adapter |
| Bundle weight | Already included | Heavier | **Lightest (~15kB core)** |
| License / cost | Free (MIT) | **Community free; Enterprise = paid** (server-side row model, pivot, Excel) | **Free (MIT)** |
| Dev effort for our grids | Low (but fight perf at scale) | Low–Med (rich out of the box) | **High** (build cells/filters/virtualization) |
| Best when… | Grids are secondary, always small server-side pages | Grids are the centerpiece and must scale | You want full control + no license cost and will invest UI effort |

## Reading of the tradeoff
- **PrimeVue DataTable (server-side only):** fewest moving parts, one dependency, zero license cost. Viable
  **if** we *always* paginate server-side with small pages (≤~100 rows) and never client-load thousands.
  Risk: the dense findings grid is exactly where it strains.
- **AG Grid:** strongest at scale, least custom code for rich grids, free Community tier covers a lot — but
  the **server-side row model** (what we'd want for OpenSearch-backed paging) and Excel export are
  **Enterprise (paid)**. Best raw fit; watch the license.
- **TanStack Table:** open-source, lightest, total control, no license cost — but you build the grid UI
  (cells, filters, virtualization) yourself. Best if we want control and accept the build effort.

## Recommendation (non-binding)
Since all list/sort/filter/aggregation is **server-side in OpenSearch** anyway (per the audit), the grid only
renders one windowed page at a time — which **narrows the perf gap**. Pragmatic path:
1. **Start with PrimeVue DataTable in strict server-side lazy mode** (already in stack, zero new deps).
2. If the dense findings grid still strains, **swap that grid (only) to TanStack Table** (free) or **AG Grid**
   (if the Enterprise features earn the license). The other docs note this as a localized change.

> Charts: **ECharts/vue-echarts — settled, no decision needed.**
> Embedding OpenSearch Dashboards as the main UI: **rejected** (double-auth, fragile multi-tenancy, no
> white-label, no triage integration) — optional internal explorer only.
