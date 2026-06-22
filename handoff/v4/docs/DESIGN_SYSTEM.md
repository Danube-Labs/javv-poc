# Design System — javv

All values are taken directly from the prototype (`prototype/JAVV Prototype.html` `:root` block and
`app/components.jsx`). Recreate these as theme tokens / PrimeVue design tokens. **Fidelity is high —
match these exactly.**

---

## 1. Brand

**javv** (lowercase wordmark) *— just another vulnerability viewer*, by **Danube Labs**.
The mark is a **magnifying glass over a river at dusk** (the "viewer" looking at the Danube).
Warm dusk palette on deep slate. See `brand/BRAND.md` and the SVGs in `brand/`.

Logo usage: `BrandIcon` is inlined as SVG in `app/components.jsx` (so it inherits crispness at any
size). Use `brand/icon.svg` / `brand/lockup.svg` / `brand/wordmark.svg` in the real app. Favicon at
`prototype/branding/favicon.svg`.

---

## 2. Color tokens

### Brand / surface (CSS custom properties)

| Token | Hex | Use |
|---|---|---|
| `--slate` | `#16232F` | Sidebar bg, dark chrome, brand mark bg, bulk-action bar |
| `--slate2` | `#21384A` | Darker accents within the mark, avatars |
| `--slate3` | `#2C4257` | Tertiary slate |
| `--bg` | `#F4F1EA` | App background (warm paper) |
| `--card` | `#FFFFFF` | Card / surface bg |
| `--panel` | `#FBFAF6` | Inset panels, table headers, hints |
| `--line` | `#E7E0D3` | Primary borders |
| `--line2` | `#F0EBE0` | Subtle inner dividers |
| `--ink` | `#1B2935` | Primary text |
| `--soft` | `#64727C` | Secondary text |
| `--muted` | `#9AA3AA` | Tertiary / disabled text |
| `--coral` | `#EC7E54` | **Brand primary** — buttons, active nav, focus ring, links |
| `--amber` | `#F4A368` | Brand secondary — mark, highlights |
| `--coral-d` | `#D96A41` | Coral hover/pressed |
| `--teal` | `#1F8E84` | Info / "server-side" notes / system accents (NOT severity) |
| `--r` | `12px` | Card radius |
| `--r-sm` | `8px` | Control radius |
| `--shadow` | `0 1px 2px rgba(22,35,47,.04), 0 8px 24px -18px rgba(22,35,47,.28)` | Card shadow |

> **Rule:** coral/amber are **brand**. They must never encode severity. Teal is for neutral
> system/info messaging only.

### Severity palette (DATA ONLY — `SEV_COLOR` in components.jsx)

Each severity has `fg` (text), `bg` (chip fill), `line` (chip border), `solid` (dot/bar/chart).

| Severity | fg | bg | line | solid |
|---|---|---|---|---|
| CRITICAL | `#B5231A` | `#FBE7E4` | `#E7C0BB` | `#C0271D` |
| HIGH | `#C2540D` | `#FCEBDD` | `#EDD0B6` | `#E2640F` |
| MEDIUM | `#9A6B05` | `#FBF1D6` | `#EBDDAE` | `#C68A12` |
| LOW | `#2F6E96` | `#E4F0F6` | `#C2DCE8` | `#3D7DA6` |
| UNKNOWN | `#5B6770` | `#ECEDEE` | `#D8DCDF` | `#74808A` |

Chart series colors (`CHART_SEV`): CRITICAL `#C0271D`, HIGH `#E2640F`, MEDIUM `#C68A12`,
LOW `#3D7DA6`, UNKNOWN `#9AA3AA`.

### Status / semantic colors

| Meaning | Text | Bg | Border |
|---|---|---|---|
| State: open | `#C2540D` | `#FCEBDD` | `#EFD3B7` |
| State: stale | `#7A7468` | `#EDEAE4` | `#DED9CF` |
| State: acknowledged | `#2F6E96` | `#E4F0F6` | `#C5DDE9` |
| State: resolved | `#2E7D4F` | `#E3F1E7` | `#C3E2CC` |
| KEV tag | `#FFFFFF` | `#8B1E16` | — |
| Health ok / sweep healthy | `#2E7D4F` / dot `#3FB37F` | `#E3F1E7` | — |
| Health degraded | `#9A6B05` | `#FBF1D6` | — |
| Health down / error | `#B5231A` | `#FBE7E4` | — |
| Scanner: Trivy tag | `#1C7A70` | `#E7F0EF` | — |
| Scanner: Grype tag | `#5A4F9E` | `#EAEAF3` | — |

Avatar tones (per-person, deterministic): `#C0271D #1F8E84 #3D7DA6 #7A5BA8 #C2540D #5C6B77 #9A6B05`.

---

## 3. Typography

Two families, loaded from Google Fonts:

- **Space Grotesk** (400/500/600/700) — all UI text, headings, body.
- **Space Mono** (400/700) — code-like data: CVE IDs, versions, namespaces, image refs, counts,
  timestamps, table-header labels, metric numbers, IDs, tokens.

| Role | Family | Size | Weight | Notes |
|---|---|---|---|---|
| Page `h1` | Grotesk | 23px | 600 | `letter-spacing:-.01em` |
| Card title `h3` | Grotesk | 14px | 600 | |
| Body / table cell | Grotesk | 12.5–13px | 400 | base `font-size:13px`, `line-height:1.5` |
| Screen subtitle | Grotesk | 13px | 400 | `--soft` |
| KPI number | Grotesk | 34px | 600 | `letter-spacing:-.03em` |
| Detail CVE `h1` | Mono | 26px | 700 | finding detail header |
| Table header | Mono | 10.5px | 600/700 | UPPERCASE, `letter-spacing:.05em`, `--soft` |
| Facet/section label | Mono | 9.5–10px | 700 | UPPERCASE, `letter-spacing:.06–.14em` |
| Small / `.sm` | — | 11px | — | |
| Mono data cell | Mono | 11–12.5px | 400 | CVEs, versions, namespaces |

---

## 4. Spacing, radius, density

- Base content padding: `22px 26px` (top/sides), `60px` bottom (for the sticky save bar in Settings).
- Screen max width: `1380px`, centered.
- Card body padding: `14px 16px`; card header `14px 16px 12px`.
- Grid gap: `16px`. Common grids: `grid-2-1` (1.55fr / 1fr), `grid-1-1` (1fr / 1fr),
  KPI strip `repeat(4,1fr)`, cluster/hero KPIs `repeat(5,1fr)`.
- Sidebar width `226px`; facet rail `218px` (Findings) / left rail on filtered screens.
- Table density: **Compact** (`tbl-dense`, ~7px row padding) is default; **Comfortable** (~9px)
  via the Columns menu toggle. Header row uses `--panel` bg.
- Radius: cards `12px`, controls/inputs/buttons `8–9px`, chips/tags `5–7px`, pills/avatars full.

---

## 5. Component inventory

These live in `app/components.jsx` and `app/filters.jsx`. Map each to a Vue/PrimeVue component.

### From `components.jsx`
| Prototype | Props | Production note |
|---|---|---|
| `BrandIcon` | `size` | Inline SVG logo. |
| `Sev` | `level, solid, dot` | Severity chip. `solid` = filled bar variant. → PrimeVue `Tag` themed. |
| `Kev` | `on` | Red "KEV" tag or em-dash. |
| `Epss` | `v` (0–1) | Mini bar + percentage. Hot ≥.7 red, warm ≥.3 orange, else grey. **EPSS is a Grype-provided signal** — only render where the row's scanner provides it. |
| `StateTag` | `state` | open/stale/acknowledged/resolved pill. |
| `ScannerTag` | `name` | Trivy/Grype colored tag. |
| `Sla` | `days, overdue` | Mono SLA chip; `overdue` = red fill. |
| `Card` | `title, subtitle, action, pad, className` | Surface w/ header. → PrimeVue `Card`/`Panel`. |
| `Chart` | `option, height` | ECharts (SVG renderer) wrapper w/ ResizeObserver. → **vue-echarts**. |
| `Spark` | `data, color` | Inline sparkline (SVG polyline). |
| `Avatar` | `initials, tone, size` | Round initials chip. |
| `MiniBar` / `MixBar` | `crit, high, med, low` | Stacked severity proportion bar. The labeled variant (counts visible, not hover-only) is used on Running images & cluster rows — keep them consistent. |
| `RelTime` | `rel, abs` | Relative text + absolute in `title` tooltip. **All timestamps use this pattern**; deadlines stay absolute. |
| `Pager` | `total, page, setPage, per, setPer, sizes` | Pagination + rows-per-page (10/25/50). → PrimeVue `Paginator`. |
| `Icon` | `name, size` | Inline stroke-icon set (grid, list, cube, shield, check, clock, search, chevron, download, filter, external, bell, alert, bookmark, columns, layers, gear, plus, trash, arrowback). → PrimeIcons or lucide. |
| `Pill` | `children, active, count` | Toggle pill. |

### From `filters.jsx` — **the reusable filtering module**
One `FIELDS` config per screen drives **both** the left facet rail and the Kibana-style filter bar,
so they can never drift apart. This is the single most important architectural pattern to preserve.

| Export | Role |
|---|---|
| `useFilters(fields, preset)` | Returns `{ sel, toggle, clearField, clearAll, hasFilters }`. `sel` is `{ fieldKey: Set<value> }`. Accepts a `preset` (from deep-links / saved views) to pre-seed selections. → **Vue composable.** |
| `FacetGroup` | One titled checkbox group with counts. |
| `FacetRail` | Renders the whole left rail from `fields` + a `countVal(field,val)` fn + optional `header` (e.g. search box). |
| `FilterBar` | Kibana-style "+ Add filter" → field picker → value multi-select; active filters render as removable pills ("Severity **is one of** CRITICAL, HIGH"). Keyboard: Esc closes, ↑/↓ navigate. Value search appears when a field has >8 values. |
| `ColumnsMenu` | Column show/hide + Compact/Comfortable density toggle. |

A **field config** looks like:
```js
{ key: "severity", label: "Severity",
  values: ["CRITICAL","HIGH","MEDIUM","LOW","UNKNOWN"],
  render: (v) => <Sev level={v} />,   // how the value renders in rail/menu
  valLabel: (v) => v }                // plain-text label for the pill
```

---

## 6. Interaction / motion

- Transitions are short and functional: nav `color .12s`, cards/rows `border-color/transform .12s`,
  switch `.15s`. No decorative animation.
- Hover: rows tint `#FBF7F0`; cards lift `translateY(-1px)` + coral border on clickable cards.
- **Focus-visible**: `2px solid var(--coral)` outline, `1px` offset — on all interactive elements.
- Dropdowns (filter bar, columns, cluster switcher, search, bell) close on outside-click and Esc.
- Sticky **save bar** in Settings: appears per section, flips "All changes saved" ↔ "You have unsaved
  changes" with Discard / Save. (It's a small shared component appended to each settings section.)

---

## 7. Responsive

Single breakpoint at ~1120px: KPI strips collapse to 2-up, `grid-2-1`/`grid-1-1` stack, and the
facet rail **stacks above** the table (the team chose stacked over a drawer). Severity-summary grids
go 3-up. The app is desktop-first (it's a dense data tool); mobile is not a target for the MVP.
