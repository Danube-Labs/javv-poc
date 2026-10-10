/**
 * A slow cluster list (issue 786). Until it arrives the grids have no rows and show their loading
 * message, which PrimeVue renders as a row of the table body. A test that takes the first body row
 * clicks that message and goes nowhere, so the shared walk must wait for a data row.
 */
import type { Page } from '@playwright/test'

// @ts-expect-error walk.mjs is the untyped shared walk module — the selector owner
import { clickDetail, DATA_ROW } from '../../scripts/walk.mjs'
import { BASE, expect, login, test } from './helpers'

async function slowClusterList(page: Page) {
  await page.route(
    (url) => url.pathname === '/api/v1/clusters',
    async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1_500))
      await route.continue()
    },
  )
}

test.beforeEach(async ({ page }) => {
  await login(page)
  await slowClusterList(page)
})

test('while the cluster list loads, the loading row is not a data row', async ({ page }) => {
  await page.goto(`${BASE}/findings`)
  await expect(page.locator('.tbl tbody tr.p-datatable-empty-message')).toBeVisible()
  await expect(page.locator(DATA_ROW)).toHaveCount(0)
  await expect(page.locator(DATA_ROW).first()).toBeVisible({ timeout: 20_000 })
})

// issue 669: the cluster list lands while the click's page is still loading. The stamp used to
// start a replace then, and the router cancelled the click: the page stayed put.
test('a click whose page is still loading when the cluster list lands still opens it', async ({ page }) => {
  let held = 0
  await page.route(
    (url) => /\/assets\/OverviewView-[^/]*\.js$/.test(url.pathname),
    async (route) => {
      held++
      await new Promise((resolve) => setTimeout(resolve, 3_000))
      await route.continue()
    },
  )
  await page.goto(`${BASE}/no-such-page`)
  await page.getByRole('heading', { name: 'Page not found' }).waitFor()
  await page.getByRole('button', { name: 'Back to Overview' }).click()
  await expect(page).toHaveURL(/\/overview\?(.*&)?cluster=/, { timeout: 10_000 })
  expect(held, 'the Overview page code was not held, so the race was not set up').toBe(1)
})

for (const [list, ready] of [
  ['/findings', '.detail-head'],
  ['/images', '.back-btn'],
]) {
  test(`the shared row click opens the first row on ${list}`, async ({ page }) => {
    const issues: string[] = []
    const opened = await clickDetail(page, BASE, list, ready, `slow-cluster-list ${list}`, issues)
    expect(issues).toEqual([])
    expect(opened).toBe(true)
  })
}
