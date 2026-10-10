/**
 * The e2e suite fails a test whose page logs a code error (issue 749, `helpers.ts`). This spec
 * proves the catching: it causes each kind on purpose, checks the fixture saw it, then empties
 * the list so the fixture lets the test pass. It also holds every spec to the helpers' `test`,
 * since one taken from Playwright directly would skip the check without a word.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { ABOUT_FILE, BASE, codeErrorLine, expect, login, test } from './helpers'

test('a page error, an app error and an uncaught rejection are each caught', async ({ page, codeErrors }) => {
  await login(page)
  // an error in a mounted hook leaves the page on screen: the boundary logs `page error`
  await page.route(ABOUT_FILE, (route) =>
    route.fulfill({
      contentType: 'application/javascript',
      body: "export default { mounted() { throw new Error('forced in mounted') }, render() { return null } }",
    }),
  )
  await page.locator('.sidebar a.side-item[href^="/about"]').click()
  await expect.poll(() => codeErrors.length, { timeout: 10_000 }).toBe(1)

  // a rejection nothing caught: the page logs `app error` and the browser reports it uncaught
  await page.evaluate(() => {
    void Promise.reject(new Error('forced rejection'))
  })
  await expect.poll(() => codeErrors.length, { timeout: 10_000 }).toBe(3)

  expect([...codeErrors].sort()).toEqual([
    'app error on /about (unhandled rejection): forced rejection',
    'page error on /about (https://vuejs.org/error-reference/#runtime-m): forced in mounted',
    'uncaught: forced rejection',
  ])
  codeErrors.length = 0 // they were caused on purpose
})

test('a code error left in place fails the test', async ({ page, codeErrors }) => {
  // the fixture's own check, after the body: the body passes, so only that check can fail it
  test.fail()
  await page.goto(`${BASE}/login`)
  await page.evaluate(() => {
    void Promise.reject(new Error('left in place'))
  })
  await expect.poll(() => codeErrors.length, { timeout: 10_000 }).toBe(2)
})

test('only the code-error events count', () => {
  const line = { level: 'error', route: '/overview', info: 'watcher callback', message: 'boom' }
  expect(codeErrorLine({ ...line, event: 'page error' })).toBe('page error on /overview (watcher callback): boom')
  expect(codeErrorLine({ ...line, event: 'app error' })).toBe('app error on /overview (watcher callback): boom')
  for (const event of ['page crashed', 'page failed to load', 'overview_load_failed']) {
    expect(codeErrorLine({ ...line, event }), event).toBeNull()
  }
  expect(codeErrorLine('Failed to load resource: the server responded with a status of 503')).toBeNull()
  expect(codeErrorLine(null)).toBeNull()
})

test('every spec takes test and expect from the helpers', () => {
  const dir = fileURLToPath(new URL('.', import.meta.url))
  const direct = readdirSync(dir)
    .filter((name) => name.endsWith('.spec.ts'))
    .filter((name) => /import \{[^}]*\b(test|expect)\b[^}]*\} from '@playwright\/test'/.test(readFileSync(dir + name, 'utf8')))
  expect(direct).toEqual([])
})
