/**
 * The width contract (DESIGN.md §layout, operator ruling 2026-07-09): data screens run the full
 * viewport via route `meta: { wide: true }` — "an internal table scrollbar beside dead margin is
 * worse than a wide table". Settings is the one ruled exception; its shell stays at the 1380px cap.
 *
 * Two routes have already shipped without it and been fixed after the fact (Overview 2026-07-16,
 * All clusters 2026-07-27, issue 485), so a new screen that forgets `wide` fails here instead of
 * reaching an operator's eyes as dead margin.
 */
import { describe, expect, it } from 'vitest'

import router from '@/router'

/** The settings subtree opts OUT — narrow forms, ruled exception to the wide default. */
const NARROW_BY_RULING = 'settings'

const shell = router.getRoutes().find((r) => r.path === '/')!

function isSettings(path: string) {
  return path === `/${NARROW_BY_RULING}` || path.startsWith(`/${NARROW_BY_RULING}/`)
}

describe('route width contract', () => {
  /** Redirect stubs render nothing, so they carry no layout obligation. */
  const screens = router
    .getRoutes()
    .filter((r) => r.components && Object.keys(r.components).length > 0)
    .filter((r) => r.path !== '/login' && r.path !== '/')

  it('every non-settings screen opts into the full viewport', () => {
    const missing = screens.filter((r) => !isSettings(r.path) && !r.meta.wide).map((r) => r.path)
    expect(
      missing,
      `screens missing \`meta: { wide: true }\` — add it, or rule the exception in DESIGN.md: ${missing.join(', ')}`,
    ).toEqual([])
  })

  it('settings stays capped', () => {
    const wideSettings = screens.filter((r) => isSettings(r.path) && r.meta.wide).map((r) => r.path)
    expect(wideSettings, 'settings is narrow by ruling').toEqual([])
  })

  it('guards against a hollow pass if the route table moves', () => {
    expect(shell).toBeDefined()
    expect(screens.length).toBeGreaterThan(10)
    expect(screens.some((r) => isSettings(r.path))).toBe(true)
  })
})
