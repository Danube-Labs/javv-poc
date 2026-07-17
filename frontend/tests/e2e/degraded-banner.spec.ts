/**
 * The OpenSearch-degraded banner (testing.md §4 spec 3, M9a observability contract): /readyz
 * down flips the banner while the CHROME stays up. The health store checks /readyz once on
 * mount (then every 30s) — intercepting BEFORE navigation makes the first check fail, so the
 * spec never waits on the poll. Recovery asserts via a clean reload, same reason.
 */
import { expect, test } from '@playwright/test'

import { BASE, login } from './helpers'

test('readyz down shows the degraded banner; the shell stays up; recovery clears it', async ({
  page,
}) => {
  await login(page)
  await page.route('**/readyz', (route) => route.fulfill({ status: 503, body: 'down' }))
  await page.goto(`${BASE}/overview`)
  const banner = page.locator('.banner[role=alert]')
  await expect(banner).toBeVisible({ timeout: 15_000 })
  // chrome stays up — degraded is a banner, never a dead app (observability.md §2)
  await expect(page.locator('.topbar')).toBeVisible()
  await page.unroute('**/readyz')
  await page.goto(`${BASE}/overview`)
  await expect(banner).toHaveCount(0)
})
