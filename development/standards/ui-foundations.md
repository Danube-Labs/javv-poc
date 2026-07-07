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
- **Space Grotesk** = all UI text/headings/body. **Space Mono** = code-like data (CVE IDs, versions,
  namespaces, image refs, counts, timestamps, IDs). **No third family. No ad-hoc sizes** - use the type-scale
  tokens (page `h1`, card title, body, KPI number, table header, mono data cell, …).

## Color - pick from the right bucket (semantic, not decorative)
Three **separate** buckets; using one where another belongs is a bug:
1. **Brand** (coral / amber / teal) - chrome, accents, info only. **Coral/amber must NEVER encode severity;
   teal is info-only.**
2. **Severity** (`crit/high/med/low/unknown`) - **DATA ONLY**, from the severity token map (`fg/bg/line/solid`
   + chart series). Never brand chrome.
3. **Status / semantic** - finding state (open/stale/acknowledged/resolved), **health (ok/degraded/down -
   the same ramp the OpenSearch-degraded banner uses, see [`observability.md`](observability.md))**, KEV tag,
   scanner tags (Trivy/Grype).

## Enforcement (the actual guardrail)
- **stylelint** in the frontend CI job (the `Frontend` gate in `.github/workflows/ci.yml`), with rules that
  **fail on raw `#hex`/`rgb()`, non-token `font-family`, and arbitrary `font-size`** in components - hard-coded
  values must come from a token. This is what stops the "10 000 style variants" drift.
- Severity/status colors are only ever read from the token map (lint/grep guard against literal severity hex).
- **Tested:** a component using a raw hex or a non-token font fails lint; the severity token map round-trips
  to the five buckets.
