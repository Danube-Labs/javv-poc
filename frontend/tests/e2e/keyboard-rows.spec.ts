/**
 * A row that opens something can be opened from the keyboard (issue 674). jsdom can prove the
 * link exists; only a browser proves Tab reaches it and Enter follows it.
 */
import type { Page } from '@playwright/test'

import { BASE, DATA_ROW, expect, login, test } from './helpers'

/** Focus the first identifier link inside `scope`, press Enter, and require the new address. */
async function openFirstRow(page: Page, scope: string, want: RegExp) {
  const link = page.locator(`${scope} a.row-link`).first()
  await expect(link).toBeVisible({ timeout: 20_000 })
  await link.focus()
  await expect(link).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(want, { timeout: 15_000 })
}

test.beforeEach(async ({ page }) => {
  await login(page)
})

test('Findings: Tab reaches a row identifier and Enter opens the finding', async ({ page }) => {
  await page.goto(`${BASE}/findings`)
  await expect(page.locator(DATA_ROW).first()).toBeVisible({ timeout: 20_000 })
  await page.locator('.tbl thead').click() // start the tab walk at the table, not the top bar
  let reached = false
  for (let i = 0; i < 40 && !reached; i++) {
    await page.keyboard.press('Tab')
    reached = await page.evaluate(() => document.activeElement?.matches('.tbl tbody a.row-link') ?? false)
  }
  expect(reached, 'Tab never landed on a row identifier').toBe(true)
  const cve = await page.evaluate(() => document.activeElement?.textContent?.trim())
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp(`/findings/${cve}\\?`), { timeout: 15_000 })
  await expect(page.locator('.detail-head')).toBeVisible()
})

test('Running images, and the findings panel on an image: Enter opens the row', async ({ page }) => {
  await page.goto(`${BASE}/images`)
  await openFirstRow(page, '.tbl tbody', /\/images\/sha256/)
  await openFirstRow(page, '.tbl tbody', /\/findings\/CVE-/)
})

test('All clusters: Enter on a cluster name opens its Overview with that cluster', async ({ page }) => {
  await page.goto(`${BASE}/clusters`)
  const link = page.locator('.fleet-card tbody a.row-link').last()
  await expect(link).toBeVisible({ timeout: 20_000 })
  const cluster = new URL((await link.getAttribute('href'))!, BASE).searchParams.get('cluster')!
  await link.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL((url) => url.pathname === '/overview' && url.searchParams.get('cluster') === cluster, {
    timeout: 15_000,
  })
})

test('Overview tables: Enter on a component, an image and a namespace each opens its target', async ({ page }) => {
  for (const [title, want] of [
    ['Top components', /\/findings\?.*q=/],
    ['Riskiest images', /\/images\/sha256/],
    ['Per namespace', /\/findings\?.*namespace=/],
  ] as const) {
    await page.goto(`${BASE}/overview`)
    const card = page.locator('section', { has: page.getByRole('heading', { name: title }) }).last()
    const link = card.locator('tbody a.row-link').first()
    await expect(link).toBeVisible({ timeout: 20_000 })
    await link.focus()
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(want, { timeout: 15_000 })
  }
})
