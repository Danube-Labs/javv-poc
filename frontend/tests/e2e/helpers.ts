/**
 * Spec helpers — selectors and the login flow come from scripts/walk.mjs (the ONE owner of
 * the route matrix, testing.md §4: "a renamed selector breaks one file, loudly").
 *
 * Every spec takes `test` and `expect` from here, not from Playwright: this `test` fails any test
 * whose page logs a code error (issue 749). That is the app logger's `page error` or `app error`
 * line, or an error the page never caught. Those leave a working page on screen, so a spec's own
 * assertions pass over them, and the Overview's `reading 'series'` went unseen that way.
 * `page crashed` and `page failed to load` are not on the list: they draw the error page, which a
 * spec sees, and `crash-page.spec.ts` causes them on purpose.
 */
import { expect, test as base, type ConsoleMessage, type Page } from '@playwright/test'

// @ts-expect-error walk.mjs is the untyped shared walk module — the selector owner
import { DATA_ROW as WALK_DATA_ROW, login as walkLogin } from '../../scripts/walk.mjs'

export const BASE = process.env.JAVV_BASE ?? 'http://localhost:4173'
/** A grid data row: never the grid's loading or empty message row (issue 786). */
export const DATA_ROW: string = WALK_DATA_ROW
export const USER = process.env.JAVV_USER ?? 'admin'
export const PASS = process.env.JAVV_PASS ?? ''

/**
 * The capability-LESS viewer seeded by `development/scripts/seed-smoke.sh` (issue 460). Proving
 * a capability gate needs a session that fails it, and the admin session can never do that.
 */
export const VIEWER = process.env.JAVV_VIEWER_USER ?? 'smoke-viewer'
export const VIEWER_PASS = process.env.JAVV_VIEWER_PASS ?? 'ci-smoke-viewer-pw'

export async function login(page: Page): Promise<void> {
  await walkLogin(page, BASE, USER, PASS)
}

export async function loginViewer(page: Page): Promise<void> {
  await walkLogin(page, BASE, VIEWER, VIEWER_PASS)
}

/** The About page's own file: `/src/views/AboutView.vue` on the dev server, a hashed chunk in a
 *  build. Specs replace it to make a page fail on purpose. */
export const ABOUT_FILE = /AboutView(\.vue|-[\w-]+\.js)(\?.*)?$/

/** The app logger's events that mean code threw and the page stayed (`system/crash.ts`). */
export const CODE_ERROR_EVENTS: readonly string[] = ['page error', 'app error']

/** One line per code error, or null for any other console message. The logger writes one object
 *  per line: `{ timestamp, level, event, ...fields }`. */
export function codeErrorLine(entry: unknown): string | null {
  if (entry === null || typeof entry !== 'object') return null
  const { event, route, info, message } = entry as Record<string, unknown>
  if (typeof event !== 'string' || !CODE_ERROR_EVENTS.includes(event)) return null
  return `${event} on ${String(route)} (${String(info)}): ${String(message)}`
}

async function consoleCodeError(msg: ConsoleMessage): Promise<string | null> {
  if (msg.type() !== 'error') return null
  const first = msg.args()[0]
  return first ? codeErrorLine(await first.jsonValue().catch(() => null)) : null
}

export const test = base.extend<{ codeErrors: string[] }>({
  // A test that causes a code error on purpose reads this list and empties it.
  codeErrors: [
    async ({ page }, use) => {
      const found: string[] = []
      const reading: Promise<void>[] = []
      page.on('console', (msg) => {
        reading.push(
          consoleCodeError(msg).then((line) => {
            if (line) found.push(line)
          }),
        )
      })
      page.on('pageerror', (err) => found.push(`uncaught: ${err.message}`))
      await use(found)
      await Promise.all(reading)
      expect(found, 'the page logged a code error').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
