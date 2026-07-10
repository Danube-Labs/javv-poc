# javv Design System — agent contract

Read this before writing or modifying any frontend code. It condenses the binding sources —
`src/styles/tokens.css` (values) · `development/standards/ui-foundations.md` (rules) ·
`handoff/v5/docs/SCREENS-v5.md` (screens) — into the one file a session needs. On any
disagreement, tokens.css + ui-foundations win.

Enforced, not advisory: **stylelint** fails raw hex/`rgb()`/non-token fonts/ad-hoc font-sizes in
components; the **style ratchet** (`src/__tests__/style-ratchet.spec.ts`) fails a color literal
anywhere else (inline styles, script, chart options) outside `styles/tokens.*` + `theme/preset.ts`,
and fails any rule pairing `--X-fg` text with its own `--X-bg` tint (the "green on green" ruling —
chips are the listed exception).

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
primary text   var(--ink)         secondary    var(--soft)
row hover      var(--row-hover)   dark chrome  var(--slate)
```
`--soft` is the CONTRAST FLOOR for text — AA (≥4.5:1) on every light surface. `--muted` is
decorative/disabled only (dashes, gauge fills, placeholder glyphs): it fails AA and must never
color words or numbers.

**VISUAL FEEDBACK IS A MUST (operator, 2026-07-10 — non-negotiable on every surface):** every
interactive element answers the pointer — hover wash + border shift (`--control-hover-bg` /
`--control-hover-line`), pressed state, row hover + link-styled target cells, focus ring. If a
user can click it, they must be able to SEE that before they click. No control ships without its
hover/pressed/focus states; reviews reject "border-shift-only" or feedback-less controls.

**Text color rules (operator rulings 2026-07-09 — verify ratios by computation, never by eye):**
- **Never same-hue text on its own tint** ("green on green"): prose/sentences on a tinted panel
  or banner are `--ink`; the hue lives in the icon, border, and background only. Chips/tags
  (short bold data labels) keep their hue pair, but every fg is AA-computed against its bg.
- **Interactive text is `--ink`** (facet rows, menu items, buttons, control labels) — `--soft`
  is for genuinely secondary annotations (counts, pager info, captions).
- **Coral as text = `--coral-text`** (pills, selected states, hover text); `--coral`/`--coral-d`
  are fills only — both fail AA as small text on light surfaces.
- **Times display 24-hour** (`hour12: false` / strict `HH:mm` inputs) — never AM/PM.
- **Solid severity chips are critical-only** (2026-07-09, finding-detail header): white text
  passes AA only on `--sev-critical-solid` (5.9:1) — every other solid fill fails with both
  white and ink. Default to the tinted chip (its pairs are gate-tested); reach for `solid`
  only for critical-grade emphasis. Side-stripe accents (the prototype's 4px `border-left`)
  stay banned — severity on a panel is carried by the chip, not a stripe.

**Interaction & spacing rulings (operator, 2026-07-10 — issue #306):**
- **Arrow cursor everywhere** — never `cursor: pointer` (desktop-app convention: Linear/Notion;
  the hand is a web-document tell). **Sharpened 2026-07-11: no I-beam either** — `base.css`
  rules `* { cursor: default }` app-wide (text and inputs included; text stays selectable),
  ECharts series carry `cursor: 'default'`, and the style ratchet fails any `cursor: pointer`
  in src. `not-allowed` on disabled stays (it's feedback — component rules outrank the
  zero-specificity universal).
- **Click affordance = row wash + link-styled TARGET cell**: the row hover wash says "this row
  is interactive"; the identifier cell that navigation anchors on (CVE now; image at M9c) turns
  `--coral-text` + underline on row hover. Transitions ~120ms ease-out with a reduced-motion
  fallback; pressed state = `--line2` wash. **Never dress a cell whose destination doesn't
  exist yet** — a false affordance is worse than a missing one.
- **Every interactive control has a VISIBLE hover** (operator, 2026-07-10): the wash
  (`--control-hover-bg`) + border shift together — a border-color shift alone cannot be seen.
  Pressed = `--control-active-bg`. One global rule in `base.css` covers the control classes;
  scoped styles may add but never remove it. Segmented controls carry inner padding + per-option
  radius so selection rings never clip against the container's corners.
- **Every overlay follows one dismiss contract** (audit #311): Escape + outside-click + a
  visible close affordance — all three, on every menu and dialog. Selection state inside any
  overlay = the coral language (`--dd-on-bg` + inset `--coral`), never an ad-hoc scheme.
- **No unbounded panels** (audit #311): any list that can grow with data gets a scroll viewport
  (sticky header) or an explicit cap note naming where the full set lives — the images-affected
  card is the reference; decisions, activity, and the rail's top-32 dims follow it. "Works with
  10 rows" is not shipped until it's been asked "and with 10,000?".
- **1024px design floor** (audit ruling, 2026-07-10): JAVV is a desktop ops dashboard — layouts
  are designed for ≥1024px (clean at 1366+, verified). Below the floor the shell keeps
  `min-width: 1024px` and scrolls as one intact piece; it never crumbles into overlapping
  chrome. A true responsive/mobile pass is an M9f decision, not an accident of flex-wrap.
- **Spacing rhythm on the `--space-*` scale** (8px base, 4px sub-grid): tight WITHIN a
  functional group (`--space-1/2`), generous BETWEEN page bands (`--space-6/8`). Uniform
  spacing everywhere is the "static" feel — page headers breathe, data clusters hold together.

### Sidebar chrome (dark slate — its own text/hover ramp, promoted from the prototype shell)
```
nav text       var(--side-fg)  hover var(--side-fg-hover) on var(--side-on-fg)/(--side-on-bg)
group label    var(--side-label)      brand word   var(--side-brand-fg)  credit var(--side-credit)
hover wash     var(--side-hover-bg)   pressed      var(--side-active-bg) footer var(--side-foot-*)
sweep dot      var(--health-ok-dot) + ring var(--sweep-ok-ring)          version var(--side-version)
```
Icons in chrome: `<AppIcon name="…">` — the javv stroke set ported verbatim from the prototype.
Never an icon font / emoji / other icon library in app chrome.

### Filter chrome (promoted from the prototype's filters CSS)
```
facet checkbox   var(--facet-check-line)      pill border   var(--fpill-line)
pill × hover     var(--fpill-x-hover-bg)      add-filter    var(--add-filter-line) / var(--add-filter-hover-bg)
dropdown         shadow var(--dd-shadow)      active item   var(--dd-on-bg)
```
The filter module itself (`FacetRail`/`FilterBar` + `filters/fields.config.ts` +
`buildFilterQuery`) is M9a-owned — screens import it and pass their own `fields` config,
never re-implement it.

## 3. Typography — two families, fixed scale

**Hanken Grotesk** (`var(--font-ui)`, operator A/B ruling 2026-07-09) = all UI text.
**Space Mono** (`var(--font-mono)`) =
code-like data: CVE IDs, versions, namespaces, image refs, counts, timestamps, table headers,
IDs. No third family, no ad-hoc sizes — the scale tokens:

```
--text-page-title 23px/600   --text-card-title 14px/600   --text-body 13px (base)
--text-kpi 34px/600          --text-detail-mono 26px mono/700
--text-table-header 10.5px mono UPPERCASE   --text-facet-label 10px mono/700 UPPERCASE
--text-sm 11px               --text-mono-cell 12.5px mono
--text-brand-word 21px       --text-nav-item 13.5px       --text-sweep-strong 11.5px
--text-control 12px (facet rows, pills, add-filter)       --text-facet-count 10.5px mono
--text-dd-item 12.5px        --text-dd-head 9.5px mono UPPERCASE
--text-quiet-action 11.5px (clear-all/clear-field text buttons)
```

## 4. Layout & density

- Sidebar `var(--sidebar-w)` (226px, slate) collapsible to `var(--sidebar-w-rail)` (64px);
  facet rail `var(--facet-rail-w)` (218px).
- Motion: `var(--ease-out)` with `var(--dur-quick)` (120ms) / `var(--dur-panel)` (200ms) —
  the only durations/curves (see §5 "Motion").
- Content: max `var(--screen-max-w)` (1380px) centered, padding `var(--content-pad)`; grid gap `var(--grid-gap)`.
  **Data-dense table screens opt out via route `meta: { wide: true }`** (full viewport width —
  operator ruling 2026-07-09: an internal table scrollbar beside dead margin is worse than a
  wide table). Findings uses it; apply to future grid-dominated screens, not dashboards.
- Radius: cards `var(--r)` (12px), controls `var(--r-sm)` (8px), chips `var(--r-chip)` (6px), pills/avatars full.
- Shadow: `var(--shadow)` on cards — nothing heavier.
- Tables: compact density default (~7px row padding); header row on `var(--panel)`, mono uppercase.
- Desktop-first; single breakpoint ~1120px (KPI strips 2-up, grids stack, facet rail stacks above the table).

## 5. Interaction

Transitions short and functional (`.12–.15s`), no decorative animation. Row hover tints
`var(--row-hover)`; clickable cards lift 1px + coral border. Focus-visible = `var(--focus-ring)`
(2px coral, 1px offset) on every interactive element. Dropdowns close on outside-click and Esc.
**At-rest clickability (operator ruling 2026-07-10):** a cell/row that NAVIGATES carries a soft
trailing chevron at rest (`--dash-muted` → `--coral-text` with the hover wash) and its
identifier takes the link treatment on hover (coral + underline, the grid's `cve-link`
convention) — hover-only affordance is not discoverable.
**Cursor (operator ruling, re-affirmed 2026-07-11):** the SYSTEM DEFAULT arrow everywhere —
never `pointer`, never the I-beam over clickable text (`cursor: default` on clickable
rows/cells; text stays selectable). Affordance comes from the chevron + wash + link treatment,
never the cursor (Linear-style desktop-app convention).

### Motion (#319) — the one scale, applied through the kit

Durations/curves come from the motion tokens (`--ease-out`, `--dur-quick` 120ms,
`--dur-panel` 200ms) — never ad-hoc values. Open/close motion is BAKED INTO the kit:
`UiDropdown` animates every menu (`t-pop`: fade + 4px rise, both ways; its `closed` event
fires after the leave for teardown that must not show mid-fade), `ModalShell` animates every
dialog entrance (`t-modal`: scrim fade + card rise; close is instant — unmount resets consumer
form state). Anything non-kit that appears/disappears in-flow (banners) wraps in
`<Transition name="t-fade">` — crossfade only, NEVER animate height/layout. All `t-*` classes
live in `base.css` and collapse under `prefers-reduced-motion`. Animate `transform`/`opacity`
only; no bounce/elastic; new appear/disappear surfaces use these classes, not new ones.

### The UI kit (`components/ui/`) — use it, never re-roll it

These components each own one contract ONCE (feedback states, dismiss behavior, rhythm). Writing
the raw markup/CSS they encapsulate is a review failure — extend the component instead:

| Component | Owns | Use for |
|---|---|---|
| `UiButton` | hover wash + pressed + focus + disabled + arrow cursor; variants `mini` / `control` / `quiet` / `ghost` / `primary` (+`block`) | every button |
| `UiSegControl` | padded seg bar, per-option radius (ring never clipped), `aria-pressed`; tones `accent` (coral selection) / `neutral` (card-lift) | any pick-one bar |
| `UiField` | mono uppercase micro-label + parenthesized `hint`, 14px band / 6px label gap (`first` zeroes the top) | any labeled control |
| `UiDropdown` | open state + outside-mousedown + document Escape + relative anchor; `trigger`/default slots (menu markup stays yours) | any popover menu |
| `ModalShell` | scrim + card + head/✕/actions, Escape + outside-click dismiss | every dialog |
| `AppIcon` | the stroke icon set | every icon |
| `ToastStack` + `useToastStore` | the confirmation channel: `success/error/info` from ANY component/store, auto-dismiss, capped stack, t-toast motion, ink text + hue on the icon | every action outcome the user would otherwise hunt for; inline contextual errors stay inline |

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
- Don't build the same panel/control twice: **anything that appears on two screens is built ONCE,
  owned by the earliest bolt that needs it, and imported everywhere else** — the filter module
  (one `fields` config drives both FacetRail and FilterBar, M9a), the lazy-grid adapter (M9f),
  the chip set (M9b), the banners (M9a). If you're copying a component to a second screen,
  stop and extract it instead.

## 7. Quick reference

```
Page bg:        var(--bg)              Card:          var(--card) + var(--r) + var(--shadow)
Panel/inset:    var(--panel)           Border:        var(--line)  / subtle var(--line2)
Text:           var(--ink) / var(--soft)   (--muted = decorative only, never text)
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

## 8. Fidelity protocol — how we stop drifting from the prototype

The gates (stylelint/ratchet) pin token *values*; they cannot see layout, icons, spacing rhythm, or
copy. Structural fidelity is a process rule:

1. **Build with the prototype open.** The reference is
   `handoff/v4/standalone/JAVV Prototype v4 (standalone).html` (open it in a browser) and its
   readable source `handoff/v4/prototype/app/*.jsx` + the CSS in `JAVV Prototype.html`. When
   building a screen/panel, extract the prototype's exact markup + CSS for that section FIRST
   (grep the class names), then port it onto tokens — don't restyle from memory.
   **Port STRUCTURE, never palette: tokens.css SUPERSEDES the prototype's colors, fonts and
   text sizes** (operator rulings 2026-07-09 — Hanken Grotesk, the AA-computed fg ramp,
   `--coral-text`, the ink-prose rule). The prototype's raw values are the *starting* promotion,
   not the current contract; a "faithful" port of its hexes would reintroduce retired,
   AA-failing colors. The contrast gate (`src/__tests__/contrast-gate.spec.ts`) enforces the
   values; this rule keeps ports from fighting it.
2. **Name the source in the PR.** A screen PR states which prototype component/classes it ports
   (e.g. "Sidebar → main.jsx `Sidebar` + `.side-*` CSS") so review can diff against it.
3. **Screenshots in every screen PR.** `/visual-test` captures the implementation; put them in the
   PR next to the prototype's rendering of the same section. (Needs the Playwright MCP wired —
   until then the operator eyeballs the dev server against the prototype tab.)
4. **Deviations are rulings, not taste.** Departing from the prototype requires a recorded reason
   (a SCREENS-v5 ruling, a shipped-backend constraint) noted in the PR — same discipline as the
   DECIDE register.

## 9. Anti-pattern detector — ruled exceptions

`npx impeccable detect` (and the `/impeccable` skill in `.claude/skills/`) is part of the
authoring loop — run it on rendered-HTML dumps of changed screens (its URL mode needs a Chrome
sandbox this environment doesn't have). Fix what it finds EXCEPT these ruled exceptions — they
are deliberate contract choices, not reflex defaults (operator ruling 2026-07-09):

| Finding | Ruling |
|---|---|
| `overused-font: Space Grotesk` | v4 brand contract. Only changes by an operator-approved token swap. |
| `cream-palette` (#f4f1ea) | The v4 warm-paper identity — deliberate palette, not a default. |
| `tiny-text 10–11.5px` on mono micro-scale | Ops-tool density (table headers, counts, chips) per the v4 scale. Body text stays ≥13px. |
| `low-contrast` white-on-coral (login/action buttons) | Prototype button treatment; 13px/600 button label, not body text. |
| `cramped-padding` on `tbl-wrap` | Full-bleed table inside the card is the prototype's design. |
| `layout-transition: width` on `.sidebar` | The collapse rail (226↔64px) — the one deliberate layout animation: user-initiated, rare, and the standard sidebar pattern (Nuxt UI reference does the same). Nothing else animates layout — the `t-*` classes are transform/opacity only. |

Everything else it flags (real contrast failures, hierarchy problems) gets fixed or gets its
own row here — never silently ignored.

## 10. Keeping this file honest

This file mirrors `tokens.css` — when a token is added/renamed, update both in the same PR (the
tokens unit test pins `CHART_SEV` to the CSS; the M9a DoD spot-check is "every token family in the
CSS has a table row here"). Values were promoted once from `handoff/v4/docs/DESIGN_SYSTEM.md`;
don't re-promote — evolve the tokens.
