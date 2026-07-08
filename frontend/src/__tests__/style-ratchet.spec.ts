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
