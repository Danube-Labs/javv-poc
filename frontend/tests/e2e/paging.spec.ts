/**
 * Server-side-everything (testing.md §4 spec 4): the findings grid pages and filters through
 * backend queries — asserted on the NETWORK, not the DOM. A page flip must ride a cursor
 * request; a filter click must re-query with the param; no interaction may change the table
 * without a backend round-trip (the no-client-side-counting hard constraint).
 */
import { expect, test } from '@playwright/test'

import { BASE, login } from './helpers'

test('grid paging and filtering go through backend queries', async ({ page }) => {
  const findingsCalls: string[] = []
  page.on('request', (r) => {
    if (r.url().includes('/api/v1/findings') && !r.url().includes('/facets'))
      findingsCalls.push(r.url())
  })
  await login(page)
  await page.goto(`${BASE}/findings`)
  await expect(page.locator('.tbl tbody tr').first()).toBeVisible({ timeout: 20_000 })
  expect(findingsCalls.length).toBeGreaterThan(0) // the rows came from the backend

  // page flip → a NEW request carrying the opaque cursor (PIT + search_after contract)
  const before = findingsCalls.length
  await page.locator('.pager-btn', { hasText: 'Next' }).first().click()
  await expect
    .poll(() => findingsCalls.slice(before).some((u) => u.includes('cursor=')), {
      timeout: 15_000,
    })
    .toBe(true)

  // filter click → a fresh query carrying the param (never a client-side slice)
  const beforeFilter = findingsCalls.length
  await page.locator('.facet-row', { hasText: 'critical' }).first().click()
  await expect
    .poll(() => findingsCalls.slice(beforeFilter).some((u) => u.includes('severity=critical')), {
      timeout: 15_000,
    })
    .toBe(true)
})
