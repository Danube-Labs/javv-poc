/**
 * App shell + login (testing.md §4 spec 1): the form is part of the smoke — never an API
 * shortcut. Wrong credentials fail loudly on the form; good ones land on /overview with the
 * chrome (sidebar + topbar) rendered.
 */
import { expect, test } from '@playwright/test'

import { BASE, USER, login } from './helpers'

test('bad credentials stay on the form with a visible error', async ({ page }) => {
  await page.goto(`${BASE}/login`)
  await page.fill('#username', USER)
  await page.fill('#password', 'not-the-password')
  await page.click('button[type=submit]')
  await expect(page.locator('[role=alert], .login-error')).toBeVisible()
  expect(page.url()).toContain('/login')
})

test('login lands on overview with the full chrome', async ({ page }) => {
  await login(page)
  await expect(page.locator('.topbar')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Findings' })).toBeVisible()
  // a protected deep link now resolves instead of bouncing to /login
  await page.goto(`${BASE}/findings`)
  await expect(page.locator('.tbl tbody tr').first()).toBeVisible({ timeout: 20_000 })
})
