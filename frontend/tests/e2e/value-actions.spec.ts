/**
 * The grid value actions (issue 349 §2) — the parts that only a real layout engine can judge.
 * jsdom returns zeroed rects, so the geometry these rules depend on is unfalsifiable in a unit
 * test; every assertion here failed as a bug in the browser first.
 *
 * 1. The bar must be REACHABLE. It overhangs its cell, so it necessarily lands in a neighbour's
 *    territory — the first version flipped row 1's bar downward and row 1 became unusable,
 *    because the seam then held two bars (row 1's hanging down, row 2's hanging up) and
 *    reaching for either moved the pointer into the other row.
 * 2. Row 1's INVERTED fill is keyed off `tr:first-child`, which is only a proxy for "the bar
 *    that lands on the header". That proxy holds because the header travels with the rows.
 *    If anyone pins the header, the wrong row gets the light bar — so the premise is asserted
 *    here rather than trusted.
 */
import { expect, test } from '@playwright/test'

import { BASE, login } from './helpers'

/**
 * The FIRST actionable cell in row 1, found rather than assumed. A fixed column index is wrong
 * across corpora: only some columns carry an action at all, and `namespace` earns one only on a
 * single-namespace row — so `td:nth-child(6)` held locally and found nothing in CI's seed.
 */
const CELL = '.p-datatable-tbody tr:nth-child(1) td:has(.val-act)'

test('first-row value actions are reachable and apply the exclusion', async ({ page }) => {
  await login(page)
  await page.goto(`${BASE}/findings`)
  await expect(page.locator(`${CELL} .val-act`).first()).toBeAttached({ timeout: 20_000 })

  // hovering reveals it; measure only once REVEALED — at rest the lift still holds the bar 4px
  // lower, so resting geometry says nothing about where the control actually sits
  await page.locator(CELL).first().hover()
  await expect(page.locator(`${CELL} .val-act-not`).first()).toBeVisible()
  await page.waitForTimeout(200) // let the 120ms lift settle before measuring

  // the bar overhangs UPWARD out of its own cell — never flipped below into the next row,
  // which is what made this row impossible to click
  const geometry = await page.locator(CELL).first().evaluate((td) => {
    const bar = td.querySelector('.val-act') as HTMLElement
    const t = td.getBoundingClientRect()
    const b = bar.getBoundingClientRect()
    return { barBottom: b.bottom, cellTop: t.top, barLeft: b.left, cellLeft: t.left }
  })
  expect(geometry.barBottom).toBeLessThanOrEqual(geometry.cellTop + 2)
  // flush on the cell's corner, not inset from it
  expect(Math.abs(geometry.barLeft - geometry.cellLeft)).toBeLessThanOrEqual(1)

  await page.locator(`${CELL} .val-act-not`).first().click()
  await expect(page).toHaveURL(/=(!|%21)/)
  // the row detail must NOT have opened — the action stops its click reaching the row
  await expect(page.locator('.slideover, [role="dialog"]')).toHaveCount(0)
})

test('the revealed bar lands on the device-pixel grid', async ({ page }) => {
  await login(page)
  await page.goto(`${BASE}/findings`)
  await expect(page.locator(`${CELL} .val-act`).first()).toBeAttached({ timeout: 20_000 })

  await page.locator(CELL).first().hover()
  // the snap is measured on the host's mouseenter, then applied through the transform
  await expect
    .poll(async () =>
      page.locator(`${CELL} .val-act`).first().evaluate((el) => {
        const r = el.getBoundingClientRect()
        // within a thousandth — the offset is rounded to 3dp, not exact binary
        return Math.max(Math.abs(r.left % 1), Math.abs(r.top % 1)) < 0.002
      }),
    )
    .toBe(true)

  // the snap was actually computed rather than defaulting away — the custom property exists.
  // NOT asserted: that the origin was fractional BEFORE. Whether this layout happens to land
  // off-grid is an environment fact (viewport, column widths), and a run where it lands whole
  // is a valid pass, not a failure. `src/__tests__/value-actions.spec.ts` proves the arithmetic
  // handles a fractional origin; this proves the applied result lands on the grid.
  const snapped = await page.locator(`${CELL} .val-act`).first().evaluate((el) => ({
    x: (el as HTMLElement).style.getPropertyValue('--snap-x'),
    y: (el as HTMLElement).style.getPropertyValue('--snap-y'),
  }))
  expect(snapped.x).not.toBe('')
  expect(snapped.y).not.toBe('')
})

test('the header travels with row 1, so the inverted-bar proxy stays true', async ({ page }) => {
  await login(page)
  await page.goto(`${BASE}/findings`)
  await expect(page.locator('.tbl tbody tr').first()).toBeVisible({ timeout: 20_000 })

  const adjacency = async () =>
    page.evaluate(() => {
      const head = document.querySelector('.p-datatable-thead')!.getBoundingClientRect()
      const row1 = document.querySelector('.p-datatable-tbody tr')!.getBoundingClientRect()
      return Math.abs(head.bottom - row1.top)
    })

  expect(await adjacency()).toBeLessThanOrEqual(2)
  // and it survives scrolling: a PINNED header would break the proxy, leaving the light bar on
  // a row that is no longer the one sitting under the band
  await page.evaluate(() => window.scrollBy(0, 400))
  expect(await adjacency()).toBeLessThanOrEqual(2)
})
