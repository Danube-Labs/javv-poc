/**
 * The style ratchet (ui-foundations §Enforcement): a component that ADDS a hand-rolled color —
 * a hex/rgb literal in a .vue file or in script outside the sanctioned token modules — fails CI.
 * The baseline below may only SHRINK, never grow: fixing a violation removes its entry; adding
 * one is a build break, not a new baseline entry.
 *
 * stylelint already rejects raw colors in CSS; this catches what it can't reach — inline `style=`
 * bindings, color literals in script (chart options, dynamic styles), template attributes.
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

const SRC = resolve(process.cwd(), 'src')

/** Files allowed to carry color literals — the token sources themselves. */
const SANCTIONED = new Set(['styles/tokens.css', 'styles/tokens.ts', 'theme/preset.ts'])

/** Known pre-existing violations. May only shrink. */
const BASELINE = new Set<string>([])

const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    if (statSync(p).isDirectory())
      return name === '__tests__' || p.endsWith('api/generated') ? [] : walk(p)
    return /\.(vue|ts|css)$/.test(name) ? [p] : []
  })
}

describe('style ratchet — no new hand-rolled colors', () => {
  const offenders = walk(SRC)
    .map((p) => relative(SRC, p).split('\\').join('/'))
    .filter((rel) => !SANCTIONED.has(rel))
    .filter((rel) => COLOR_LITERAL.test(readFileSync(join(SRC, rel), 'utf8')))

  it('no color literals outside the sanctioned token modules', () => {
    const added = offenders.filter((f) => !BASELINE.has(f))
    expect(
      added,
      `hand-rolled color literal(s) — use tokens.css / tokens.ts instead (ui-foundations): ${added.join(', ')}`,
    ).toEqual([])
  })

  it('baseline only shrinks (remove fixed entries)', () => {
    const stale = [...BASELINE].filter((f) => !offenders.includes(f))
    expect(stale, `fixed — delete from BASELINE: ${stale.join(', ')}`).toEqual([])
  })
})

/**
 * "System arrow everywhere" (DESIGN.md §2, operator ruling 2026-07-10; bitten twice by
 * 2026-07-11 — ECharts series, then the sidebar anchors): `cursor: pointer` is banned in app
 * code. base.css rules the arrow globally; ECharts series carry `cursor: 'default'`
 * (overview-charts.spec pins those). Nothing may opt back into the hand.
 */
describe('style ratchet — no pointer cursor', () => {
  it('no `cursor: pointer` anywhere in src', () => {
    const hits = walk(SRC)
      .map((p) => relative(SRC, p).split('\\').join('/'))
      .filter((rel) => /cursor:\s*['"]?pointer/.test(readFileSync(join(SRC, rel), 'utf8')))
    expect(
      hits,
      `pointer cursor(s) — the arrow is ruled app-wide (DESIGN.md §2): ${hits.join(', ')}`,
    ).toEqual([])
  })
})

/**
 * "Never same-hue text on its own tint" (DESIGN.md §2, operator ruling 2026-07-09; bitten twice
 * by 2026-07-10): a rule block that pairs `color: var(--X-fg)` with `background: var(--X-bg)`
 * of the SAME hue family ships low-contrast prose. Chips/tags are the ruled exception (short
 * bold data labels with gate-tested pairs) — they live in components/chips/ or match a chip
 * selector below.
 */
const CHIP_EXEMPT = [/^components\/chips\//]
const CHIP_SELECTOR =
  // chip-class: short bold data labels with gate-tested pairs, plus the sidebar's own dark ramp
  // (incl. the table-head band — B2 ruling 2026-07-16: slate2 + parchment, ~10:1 — the
  // triage-panel head that joined the same band per the 2026-07-17 ruling, and the inspector
  // cards' panel-band that joined it 2026-07-18)
  /\.(time-range-hist|kev-tag|kev-lg|both-tag|state-opt-on|vm-fp|vm-ne|side-item|tbl|triage-head|so-head|card-head|assignee-none|panel-band)\b/

describe('style ratchet — no same-hue text on its own tint', () => {
  const files = walk(SRC)
    .map((p) => relative(SRC, p).split('\\').join('/'))
    .filter((rel) => /\.(vue|css)$/.test(rel) && !SANCTIONED.has(rel))
    .filter((rel) => !CHIP_EXEMPT.some((re) => re.test(rel)))

  it('prose on a tinted panel uses --ink; the hue stays in icon/border/background', () => {
    const hits: string[] = []
    for (const rel of files) {
      const css = readFileSync(join(SRC, rel), 'utf8')
      // each rule block: selector { declarations }
      for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
        const selector = m[1] ?? ''
        const body = m[2] ?? ''
        if (CHIP_SELECTOR.test(selector)) continue
        const fg = body.match(/color:\s*var\(--([a-z0-9-]+)-fg\)/)
        const bg = body.match(/background(?:-color)?:\s*var\(--([a-z0-9-]+)-bg\)/)
        if (fg && bg && fg[1] === bg[1]) hits.push(`${rel} → ${selector.trim().split('\n').pop()}`)
      }
    }
    expect(
      hits,
      `same-hue fg/bg pair(s) — prose on a tint is var(--ink), hue goes to icon/border/bg (DESIGN.md §2): ${hits.join('; ')}`,
    ).toEqual([])
  })
})
