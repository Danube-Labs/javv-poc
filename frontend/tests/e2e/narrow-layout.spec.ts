/**
 * Layout at the 1024 design floor (issue 667). jsdom has no layout, so only a browser can prove
 * that one box does not sit on another or push the page sideways.
 */
import { expect, test } from '@playwright/test'

import { BASE, login } from './helpers'

test.use({ viewport: { width: 1024, height: 800 } })

test.beforeEach(async ({ page }) => {
  await login(page)
})

test('Settings: a section tab shows its whole label, with the scope dot beside it', async ({ page }) => {
  await page.goto(`${BASE}/settings`)
  await expect(page.locator('.snav-item').first()).toBeVisible({ timeout: 20_000 })
  const overlaps = await page.evaluate(() =>
    [...document.querySelectorAll('.snav-item')].map((item) => {
      const label = item.querySelector('span')!.getBoundingClientRect()
      const dot = item.querySelector('.scope-dot')!.getBoundingClientRect()
      return { tab: item.textContent!.trim(), overlap: Math.round(label.right - dot.left) }
    }),
  )
  expect(overlaps.length).toBeGreaterThan(0)
  expect(overlaps.filter((o) => o.overlap > 0)).toEqual([])
})
