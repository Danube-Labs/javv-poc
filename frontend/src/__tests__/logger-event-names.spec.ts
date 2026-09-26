/**
 * The beacon's name filter, closed at build time (issue 525). `lib/logger.ts` drops any warn/error
 * whose event name the server would 422, deliberately without counting it — so a call site with a
 * bad name reports NOTHING, ever. Event names are source literals, so this sweeps them and fails CI
 * on one that could never ship, instead of letting it go silent in production.
 *
 * Checked against the logger's own exported pattern, never a copy: drift between two copies is
 * exactly what this exists to catch. Specs are excluded — `client-events-beacon.spec.ts` holds
 * invalid names on purpose, to prove the runtime filter.
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { BEACON_EVENT_NAME } from '@/lib/logger'

const SRC = resolve(process.cwd(), 'src')

/** Files that pass a caller-supplied name through to the logger, and how those names are swept. */
const PASS_THROUGH = new Map([['composables/useCsvExport.ts', 'useCsvExport({ event })']])

/** A shipped (warn/error) call and its first argument, whatever it is. */
const CALL = /\blogger\s*\.\s*(?:warn|error)\s*\(\s*([^,)]*)/g
/** A plain quoted literal; the raw text is what gets tested, so any escape fails the pattern. */
const LITERAL = /^(['"])(.*)\1$/s
/** How far past `useCsvExport(` its options object may put the `event` key. */
const CSV_WINDOW = 1_000

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    if (statSync(p).isDirectory())
      return name === '__tests__' || p.endsWith('api/generated') ? [] : walk(p)
    return /\.(vue|ts)$/.test(name) && !/\.(spec|test)\.ts$/.test(name) ? [p] : []
  })
}

type Site = { file: string; name: string }

function sweep() {
  const names: Site[] = []
  const computed: string[] = []
  const csvWithoutLiteral: string[] = []
  for (const path of walk(SRC)) {
    const file = relative(SRC, path).split('\\').join('/')
    const text = readFileSync(path, 'utf8')
    for (const [, arg] of text.matchAll(CALL)) {
      const literal = LITERAL.exec(arg!.trim())
      if (literal) names.push({ file, name: literal[2]! })
      else if (!PASS_THROUGH.has(file)) computed.push(`${file}: ${arg!.trim()}`)
    }
    for (const call of text.matchAll(/\buseCsvExport\s*\(/g)) {
      if (file === 'composables/useCsvExport.ts') continue // the definition, not a call
      const window = text.slice(call.index, call.index + CSV_WINDOW)
      const event = /\bevent\s*:\s*(['"])([^'"\n]*)\1/.exec(window)
      if (event) names.push({ file, name: event[2]! })
      else csvWithoutLiteral.push(file)
    }
  }
  return { names, computed, csvWithoutLiteral }
}

describe('beacon event names are shippable (issue 525)', () => {
  const { names, computed, csvWithoutLiteral } = sweep()

  it('every warn/error event name matches the server pattern', () => {
    const bad = names.filter((s) => !BEACON_EVENT_NAME.test(s.name))
    expect(
      bad.map((s) => `${s.file}: '${s.name}'`),
      `the beacon drops these silently — rename to match ${BEACON_EVENT_NAME}`,
    ).toEqual([])
  })

  it('no computed event names outside the known pass-throughs', () => {
    expect(
      computed,
      `a computed name is invisible to this guard — pass a literal, or add a pass-through here together with a sweep of the literals its callers supply`,
    ).toEqual([])
    expect(csvWithoutLiteral, 'useCsvExport needs a literal `event` for this sweep').toEqual([])
  })

  it('the sweep actually reaches the call sites (it cannot pass on zero matches)', () => {
    const found = new Set(names.map((s) => s.name))
    expect(found).toContain('backend degraded') // spaces are legal, and this one ships the 503
    expect(found).toContain('approvals_export_failed') // reached only through the pass-through
    expect(names.length).toBeGreaterThan(50)
  })
})
