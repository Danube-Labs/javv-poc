# javv Design System — agent contract

Read this before writing or modifying any frontend code. It condenses the binding sources —
`src/styles/tokens.css` (values) · `development/standards/ui-foundations.md` (rules) ·
`handoff/v5/docs/SCREENS-v5.md` (screens) — into the one file a session needs. On any
disagreement, tokens.css + ui-foundations win.

Enforced, not advisory: **stylelint** fails raw hex/`rgb()`/non-token fonts/ad-hoc font-sizes in
components; the **style ratchet** (`src/__tests__/style-ratchet.spec.ts`) fails a color literal
anywhere else (inline styles, script, chart options) outside `styles/tokens.*` + `theme/preset.ts`.

## 1. Visual theme

Warm, editorial, data-dense. Warm-paper background (`#F4F1EA`) with white cards, **dark-slate
chrome** (sidebar/brand marks on `#16232F`), coral as the single brand accent. Single light theme
by contract — no dark mode, no `prefers-color-scheme` styling (the slate sidebar is chrome, not a
theme). High information density: subtle borders and panel tints, almost no decorative shadow.

## 2. Color — pick from the right bucket (wrong bucket = bug)

| Bucket | Tokens | Rule |
|---|---|---|
| **Brand** | `--coral` `--coral-d` `--amber` `--teal` `--slate*` | Chrome, buttons, active nav, focus, links. Coral/amber must **never** encode severity. Teal = info only. |
| **Severity** | `--sev-<severity>-{fg,bg,line,solid}` | **DATA ONLY.** Six D46 canonicals: `critical high medium low negligible unknown`. `negligible` is muted, never red (A-1). From script use `SEV_COLOR` / `CHART_SEV` (`@/styles/tokens`). |
| **Status** | `--state-<open\|stale\|ack\|resolved>-*` · `--health-{ok,degraded,down}-*` · `--kev-*` · `--scanner-{trivy,grype}-*` | Finding state pills, health ramp (the same ramp as the degraded banner), KEV tag, scanner tags. |

### Surfaces & text
```
page bg        var(--bg)          cards        var(--card)
inset/panel    var(--panel)       borders      var(--line)   subtle: var(--line2)
primary text   var(--ink)         secondary    var(--soft)   tertiary: var(--muted)
row hover      var(--row-hover)   dark chrome  var(--slate)
```

## 3. Typography — two families, fixed scale

**Space Grotesk** (`var(--font-ui)`) = all UI text. **Space Mono** (`var(--font-mono)`) =
code-like data: CVE IDs, versions, namespaces, image refs, counts, timestamps, table headers,
IDs. No third family, no ad-hoc sizes — the scale tokens:

```
--text-page-title 23px/600   --text-card-title 14px/600   --text-body 13px (base)
--text-kpi 34px/600          --text-detail-mono 26px mono/700
--text-table-header 10.5px mono UPPERCASE   --text-facet-label 10px mono/700 UPPERCASE
--text-sm 11px               --text-mono-cell 12.5px mono
```

## 4. Layout & density

- Sidebar `var(--sidebar-w)` (226px, slate); facet rail `var(--facet-rail-w)` (218px).
- Content: max `var(--screen-max-w)` (1380px) centered, padding `var(--content-pad)`; grid gap `var(--grid-gap)`.
- Radius: cards `var(--r)` (12px), controls `var(--r-sm)` (8px), chips `var(--r-chip)` (6px), pills/avatars full.
- Shadow: `var(--shadow)` on cards — nothing heavier.
- Tables: compact density default (~7px row padding); header row on `var(--panel)`, mono uppercase.
- Desktop-first; single breakpoint ~1120px (KPI strips 2-up, grids stack, facet rail stacks above the table).

## 5. Interaction

Transitions short and functional (`.12–.15s`), no decorative animation. Row hover tints
`var(--row-hover)`; clickable cards lift 1px + coral border. Focus-visible = `var(--focus-ring)`
(2px coral, 1px offset) on every interactive element. Dropdowns close on outside-click and Esc.

## 6. Do / Don't

**Do**
- Reference tokens for every color, font, size, radius, shadow, and layout constant.
- Use `SEV_COLOR` / `CHART_SEV` / `STATE_COLOR` / `SCANNER_COLOR` from `@/styles/tokens` in script.
- Render per-scanner numbers side-by-side — **never summed, merged, or averaged** (per-scanner sacred).
- Use the real brand SVGs from `design/brand/` (dark variants in dark chrome) — never redraw them.
- Timestamps: relative text + absolute in the `title` tooltip; deadlines stay absolute.

**Don't**
- No raw `#hex` / `rgb()` / `hsl()` anywhere outside `styles/tokens.*` + `theme/preset.ts` (CI-enforced).
- No `font-family`/`font-size` literals — type-scale tokens only (CI-enforced).
- Never encode severity with brand colors, or brand chrome with severity colors.
- No purple/indigo defaults, no gradients, no rounded-everything, no shadow stacking — this app has
  a specific look; PrimeVue chrome is themed through `theme/preset.ts`, don't fight it inline.
- Don't hand-roll a severity/state/scanner chip — use (or create in M9b) the shared chip components.

## 7. Quick reference

```
Page bg:        var(--bg)              Card:          var(--card) + var(--r) + var(--shadow)
Panel/inset:    var(--panel)           Border:        var(--line)  / subtle var(--line2)
Text:           var(--ink) / var(--soft) / var(--muted)
Brand action:   var(--coral), hover var(--coral-d)
Severity chip:  color var(--sev-critical-fg); background var(--sev-critical-bg);
                border-color var(--sev-critical-line)   (× six severities)
Chart series:   CHART_SEV.critical … (from '@/styles/tokens' — pinned to tokens.css by test)
State pill:     var(--state-open-*) etc.   Health dot: var(--health-ok-dot)
Mono data:      font-family var(--font-mono); font-size var(--text-mono-cell)
Focus:          outline: var(--focus-ring); outline-offset: 1px
```

### Example component pattern
```vue
<template>
  <section class="card">
    <h3>Findings by severity</h3>
    <span class="chip" :data-sev="sev">{{ sev }}</span>
  </section>
</template>

<style scoped>
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 14px 16px;
}
.chip {
  border-radius: var(--r-chip);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  text-transform: uppercase;
}
.chip[data-sev='critical'] {
  color: var(--sev-critical-fg);
  background: var(--sev-critical-bg);
  border: 1px solid var(--sev-critical-line);
}
</style>
```

## 8. Keeping this file honest

This file mirrors `tokens.css` — when a token is added/renamed, update both in the same PR (the
tokens unit test pins `CHART_SEV` to the CSS; the M9a DoD spot-check is "every token family in the
CSS has a table row here"). Values were promoted once from `handoff/v4/docs/DESIGN_SYSTEM.md`;
don't re-promote — evolve the tokens.
