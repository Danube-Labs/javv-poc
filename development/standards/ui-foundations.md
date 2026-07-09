# UI foundations

How JAVV keeps **one** visual system instead of a thousand ad-hoc fonts, sizes, and hex codes. The design
*substance* is already strong (palette, type scale, semantic-color discipline) - this doc makes it
**binding and enforced**, not just reference.

> Owned by **M9a** (creates the tokens + wires the linter); every later FE bolt (M9b-f) consumes the tokens,
> never raw values.

## Single source of truth = tokens
- **`frontend/src/styles/tokens.css` + `tokens.ts` (M9a) are the binding source.** Components reference
  **tokens only** - never a raw `#hex`, never a literal `font-family`, never an arbitrary `font-size`.
- **Provenance:** the *values* come from [`.deprecated/docs/engineering/UI-GUIDELINES.md`](../../.deprecated/docs/engineering/UI-GUIDELINES.md)
  (the original v1 UI target, archived) + [`handoff/v4/docs/DESIGN_SYSTEM.md`](../../handoff/v4/docs/DESIGN_SYSTEM.md)
  (reference fidelity). They are **promoted into the tokens once**; this doc does **not** re-host hex values
  (re-hosting drifts - point, don't copy). Tokens carry light **and** dark variants.
- PrimeVue is themed **through** the tokens (theme bridge), so component chrome and custom CSS share one scale.

## Typography - two families, fixed scale
- **Hanken Grotesk** = all UI text/headings/body (operator A/B ruling 2026-07-09, replacing Space
  Grotesk). **Space Mono** = code-like data (CVE IDs, versions, namespaces, image refs, counts,
  timestamps, IDs). **No third family. No ad-hoc sizes** - use the type-scale tokens (page `h1`,
  card title, body, KPI number, table header, mono data cell, …).

## Contrast - AA is the floor (ruled 2026-07-09)
- Every piece of **text** meets WCAG AA (≥4.5:1) on its surface: `--soft` is the darkest-allowed
  "quiet" text (AA on all light surfaces); `--muted` is **decorative/disabled only** (dashes, gauge
  fills) and must never color words or numbers. Dark-chrome text uses the AA-checked `--side-*`
  ramp. Teal as text = `--teal-text`, never `--teal`.
- Ruled exceptions (brand contract, documented in `frontend/DESIGN.md` §9): white-on-coral
  action/selected chips and the dense mono micro-scale.

## Color - pick from the right bucket (semantic, not decorative)
Three **separate** buckets; using one where another belongs is a bug:
1. **Brand** (coral / amber / teal) - chrome, accents, info only. **Coral/amber must NEVER encode severity;
   teal is info-only.**
2. **Severity** (`critical/high/medium/low/negligible/unknown` - the six D46 full-word canonicals;
   `negligible` renders muted, never red, per the A-1 ruling) - **DATA ONLY**, from the severity token
   map (`fg/bg/line/solid` + chart series). Never brand chrome.
3. **Status / semantic** - finding state (open/stale/acknowledged/resolved), **health (ok/degraded/down -
   the same ramp the OpenSearch-degraded banner uses, see [`observability.md`](observability.md))**, KEV tag,
   scanner tags (Trivy/Grype).

## Enforcement (the actual guardrail)
- **stylelint** in the frontend CI job (the `Frontend` gate in `.github/workflows/ci.yml`), with rules that
  **fail on raw `#hex`/`rgb()`, non-token `font-family`, and arbitrary `font-size`** in components - hard-coded
  values must come from a token. This is what stops the "10 000 style variants" drift.
- Severity/status colors are only ever read from the token map (lint/grep guard against literal severity hex).
- **Style ratchet (M9a):** a pinned test fails CI when a component **adds** a hand-rolled severity/status
  color that bypasses the token map/badge helpers; the recorded baseline may only shrink, never grow.
  stylelint catches raw hex/fonts - the ratchet catches *semantic* bypasses (a literal red where the
  severity token belongs).
- **Tested:** a component using a raw hex or a non-token font fails lint; the severity token map round-trips
  to the six buckets.
- **Agent-facing condensation:** `frontend/DESIGN.md` (an M9a deliverable) is the one file a session reads
  before writing FE code - token tables (light+dark), do's/don'ts, quick reference, example patterns. It
  *derives from* the tokens and this doc; on disagreement, `tokens.css` + this doc win.
