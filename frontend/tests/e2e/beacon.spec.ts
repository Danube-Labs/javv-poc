/**
 * The client-events beacon at the browser seam — issue 520 slice 4 (issue 519 item 3).
 *
 * The unit tests (`client-events-beacon.spec.ts`) mock the transport, and the smoke's section 6c
 * POSTs to the route with curl. Neither proves the seam between them: a real call site in the
 * BUILT app, `sendBeacon` carrying the session cookie, and the backend re-emitting the event into
 * its own log. That log line is the evidence an operator actually reads, so it is what this spec
 * asserts on.
 *
 * Needs the backend's stdout in `development/e2e/logs/backend.log`, which is where CI's
 * frontend-smoke job and the RUNNING-THE-STACK recipe both write it.
 */
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { expect, test } from '@playwright/test'

import { BASE, USER, login } from './helpers'

const BACKEND_LOG = fileURLToPath(
  new URL('../../../development/e2e/logs/backend.log', import.meta.url),
)

type LogLine = {
  event?: string
  level?: string
  client_event?: boolean
  username?: string
  fields?: Record<string, unknown>
}

/** The `client.inspect_rejected` lines carrying this run's marker. The marker is unique per run,
 *  so a line left in the file by an earlier run (or another backend sharing it) cannot match. */
function rejectedLines(marker: string): LogLine[] {
  const found: LogLine[] = []
  for (const raw of readFileSync(BACKEND_LOG, 'utf8').split('\n')) {
    if (!raw.includes(marker)) continue
    try {
      const line = JSON.parse(raw) as LogLine
      if (line.event === 'client.inspect_rejected') found.push(line)
    } catch {
      // not a JSON line (uvicorn's own access lines share the stream)
    }
  }
  return found
}

test('a browser-side warning lands in the backend log as a client.<name> line', async ({
  page,
}) => {
  expect(existsSync(BACKEND_LOG), `no backend log at ${BACKEND_LOG}`).toBe(true)

  const marker = `beacon-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  // three segments fail the "<index>/<verb>" shape check with a 422 before any index is read, so
  // the rejection does not depend on what the seeded store holds
  const path = `${marker}/_search/x`

  await login(page)
  await page.goto(`${BASE}/inspect`)
  await expect(page.locator('.idx, .load-error').first()).toBeVisible({ timeout: 20_000 })
  await page.locator('.pathbox').fill(path)
  await page.locator('.pathbox').press('ControlOrMeta+Enter')
  // the call site: InspectView logs `inspect_rejected` at warn, which queues it for the beacon
  await expect(page.locator('.reject')).toContainText('422', { timeout: 20_000 })

  // Flush now rather than waiting out the 5 s batching window: `pagehide` is one of the beacon's
  // two unload signals (lib/logger.ts). The request is observed, not assumed. Its body is not:
  // Chromium does not expose a sendBeacon payload to Playwright (postData() reads ""), so the
  // content is proven where it matters, by the log line below.
  const beacon = page.waitForRequest(
    (r) => r.url().endsWith('/api/v1/client-events') && r.method() === 'POST',
    { timeout: 10_000 },
  )
  await page.evaluate(() => window.dispatchEvent(new Event('pagehide')))
  await beacon

  await expect
    .poll(() => rejectedLines(marker).length, {
      timeout: 15_000,
      message: `no client.inspect_rejected line for ${marker} in ${BACKEND_LOG}`,
    })
    .toBe(1)
  const [line] = rejectedLines(marker)
  expect(line!.level).toBe('warning')
  expect(line!.client_event).toBe(true)
  // attributed from the session the beacon carried, never from anything the browser sent
  expect(line!.username).toBe(USER)
  // the call site's fields arrive nested under `fields`, not splatted into the line
  expect(line!.fields).toMatchObject({ path, status: 422 })
})
