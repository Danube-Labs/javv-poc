/**
 * The Audit log's sidebar entry opens it without sign-ins (issue 681), as a filter the user can
 * see and remove. Only a browser proves the link, the chip and the rows agree.
 */

import { BASE, DATA_ROW, expect, login, test } from './helpers'

test('the sidebar opens the Audit log with a removable "not Login" filter', async ({ page }) => {
  await login(page)
  await page.goto(`${BASE}/overview`)
  const link = page.locator('a.side-item', { hasText: 'Audit log' })
  await link.click()
  await expect(page).toHaveURL(/\/audit\?.*action=(!|%21)login/, { timeout: 15_000 })
  await expect(link).toHaveClass(/router-link-active/)

  const chip = page.locator('.fpill', { hasText: 'Action' })
  await expect(chip).toContainText('Login', { timeout: 20_000 })
  await expect(chip).toContainText('not')
  await page.waitForLoadState('networkidle')
  // every sign-in row is gone; the suite's own login guarantees at least one exists in the store
  await expect(page.locator('.tbl tbody td .action-tag', { hasText: /^\s*Login\s*$/ })).toHaveCount(0)

  // removing the chip brings them back, and the address drops the filter
  await chip.locator('.fpill-x').click()
  await expect(page).not.toHaveURL(/action=/)
  await expect(page.locator(DATA_ROW, { hasText: 'Login' }).first()).toBeVisible({ timeout: 20_000 })
})
