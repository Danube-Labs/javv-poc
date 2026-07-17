/**
 * The core triage round-trip (testing.md §4 spec 2, the M9b core-loop gate): grid → finding →
 * flip open⇄acknowledged → journaled save → the state SURVIVES a reload (server truth, not
 * client echo) → revert, leaving the store as found. The reload re-reads the findings index,
 * which refreshes ~1s behind the write — poll the reload, never assert once.
 */
import { expect, test } from '@playwright/test'

import { BASE, login } from './helpers'

test('a triage action persists across reload, then is reverted', async ({ page }) => {
  await login(page)
  await page.goto(`${BASE}/findings`)
  await page.locator('.tbl tbody tr').first().click()
  await expect(page.locator('.detail-head')).toBeVisible({ timeout: 20_000 })
  const url = page.url()

  const ack = page.locator('.state-opt', { hasText: 'Acknowledge' })
  const open = page.locator('.state-opt', { hasText: 'Open' })
  const save = page.locator('button', { hasText: 'Save to audit trail' })
  const isOn = async (loc: typeof ack) =>
    ((await loc.getAttribute('class')) ?? '').includes('state-opt-on')

  await expect(ack).toBeEnabled()
  const wasAcked = await isOn(ack)
  await (wasAcked ? open : ack).click()
  await save.click()
  await page.waitForLoadState('networkidle')

  await expect
    .poll(
      async () => {
        await page.goto(url)
        await page.locator('.detail-head').waitFor({ timeout: 15_000 })
        return isOn(ack)
      },
      { timeout: 20_000, intervals: [1_000] },
    )
    .toBe(!wasAcked)

  // revert — the seeded store is shared with the route walk; leave it as found
  await (wasAcked ? ack : open).click()
  await save.click()
  await page.waitForLoadState('networkidle')
  await expect
    .poll(
      async () => {
        await page.goto(url)
        await page.locator('.detail-head').waitFor({ timeout: 15_000 })
        return isOn(ack)
      },
      { timeout: 20_000, intervals: [1_000] },
    )
    .toBe(wasAcked)
})
