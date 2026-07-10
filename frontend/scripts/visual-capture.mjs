/**
 * The authoring-time visual rig (/visual-test, issue #301) — committed so it survives sessions.
 *
 * Logs in through the real form, walks the app INCLUDING forced non-default states (the history
 * banner hid an AA failure from defaults-only scans), and writes per-state screenshots + rendered
 * HTML dumps for the anti-pattern detector:
 *
 *   JAVV_USER=admin JAVV_PASS=… node scripts/visual-capture.mjs [outDir]
 *   node ../.claude/skills/impeccable/scripts/detect.mjs <outDir>/*.html
 *
 * Notes for agents: kill the node child by PID/port, never `pkill -f`; the SPA answers 200 HTML
 * for any GET — verify proxied responses by body; viewport is set before any navigation.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.env.JAVV_BASE ?? 'http://localhost:5173'
// default output anchors to the REPO-ROOT .playwright-mcp (one artifact dir to purge) — a
// cwd-relative default is how a second copy under frontend/ once accumulated 40MB unnoticed
const REPO_ROOT_OUT = new URL('../../.playwright-mcp/visual-test/', import.meta.url).pathname
const OUT =
  process.argv[2] ?? `${REPO_ROOT_OUT}${new Date().toISOString().slice(0, 19).replaceAll(':', '-')}`
const USER = process.env.JAVV_USER
const PASS = process.env.JAVV_PASS
if (!USER || !PASS) {
  console.error('set JAVV_USER and JAVV_PASS (dev creds — never hardcode them here)')
  process.exit(2)
}

const issues = []
const pad = (n) => String(n).padStart(2, '0')

async function shot(page, name, { dump = false, clip } = {}) {
  await page.screenshot({ path: `${OUT}/${name}.png`, ...(clip ? { clip } : {}) })
  if (dump) writeFileSync(`${OUT}/${name}.html`, await page.content())
  console.log('  captured', name + (dump ? ' (+html dump)' : ''))
}

async function main() {
  mkdirSync(OUT, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } })
  page.on('console', (m) => {
    if (m.type() === 'error' || m.type() === 'warning') issues.push(`[console.${m.type()}] ${m.text()}`)
  })
  page.on('pageerror', (e) => issues.push(`[pageerror] ${e.message}`))

  // login (pre-auth state, then the real form)
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  await shot(page, '01-login', { dump: true })
  await page.fill('#username', USER)
  await page.fill('#password', PASS)
  await page.click('button[type=submit]')
  await page.waitForURL('**/overview', { timeout: 10_000 })
  await page.waitForLoadState('networkidle')
  await shot(page, '02-shell-overview', { dump: true })

  // findings — default state
  await page.goto(`${BASE}/findings`)
  await page.waitForSelector('.tbl tbody tr', { timeout: 10_000 })
  await page.waitForLoadState('networkidle')
  await shot(page, '03-findings-default', { dump: true })

  // findings — filtered (pills + URL sync)
  await page.locator('.facet-row', { hasText: 'critical' }).first().click()
  await page.waitForTimeout(700)
  await shot(page, '04-findings-filtered', { dump: true })
  await page.locator('.clear-all').click()
  await page.waitForTimeout(400)

  // time menu open
  await page.click('.time-range')
  await page.waitForSelector('.time-menu')
  await shot(page, '05-time-menu', { clip: { x: 240, y: 0, width: 1400, height: 560 } })

  // FORCED STATE: history (absolute past range) — banners never render in defaults-only dumps
  const past = new Date(Date.now() - 3_600_000)
  const d = `${past.getFullYear()}-${pad(past.getMonth() + 1)}-${pad(past.getDate())}`
  const hm = `${pad(past.getHours())}:${pad(past.getMinutes())}`
  await page.fill('input[aria-label="Range start date"]', d)
  await page.fill('input[aria-label="Range start time (24h)"]', '00:00')
  await page.fill('input[aria-label="Range end date"]', d)
  await page.fill('input[aria-label="Range end time (24h)"]', hm)
  await page.locator('.time-abs .time-apply').click()
  await page.waitForSelector('.history-banner', { timeout: 5_000 })
  await page.waitForTimeout(700)
  await shot(page, '06-history-state', { dump: true })
  await page.click('.time-range')
  await page.locator('.back-now').click()
  await page.waitForTimeout(400)

  // columns menu open
  await page.locator('.cols-dd .ui-btn').click()
  await page.waitForSelector('.cols-menu')
  await shot(page, '07-columns-menu')
  await page.keyboard.press('Escape')

  // export + bulk dialogs (slice 4) — DRAFT ONLY, never submitted
  await page.locator('.export-wrap .ui-btn').click()
  await page.waitForSelector('.modal')
  await shot(page, '07b-export-dialog', { dump: true })
  await page.keyboard.press('Escape')
  await page.locator('.facet-row', { hasText: 'critical' }).first().click()
  await page.waitForTimeout(600)
  if (await page.locator('.bulk-wrap .ui-btn').count()) {
    await page.locator('.bulk-wrap .ui-btn').click()
    await page.waitForSelector('.modal')
    await shot(page, '07c-bulk-dialog', { dump: true })
    await page.keyboard.press('Escape')
  } else {
    console.log('  (bulk hidden — principal lacks can_triage: RBAC state captured implicitly)')
  }
  await page.locator('.clear-all').click()
  await page.waitForTimeout(500)

  // finding detail — row click navigates (cve + digest + scanner identity)
  await page.locator('.tbl tbody tr').first().click()
  await page.waitForSelector('.detail-head', { timeout: 10_000 })
  await page.waitForLoadState('networkidle')
  await shot(page, '08-finding-detail', { dump: true })

  // FORCED STATE: triage draft (vex chips) + risk-accept dialog — DRAFT ONLY, never saved:
  // mutations in automated visual runs are confirmation-gated (standing rule)
  const naBtn = page.locator('.state-opt', { hasText: 'Not affected' })
  if (await naBtn.count()) {
    if (await naBtn.isDisabled()) {
      // a viewer principal: the locked panel IS the forced state worth capturing
      await shot(page, '08b-triage-locked', { dump: true })
    } else {
      await naBtn.click()
      await page.waitForSelector('.vex-chips')
      await shot(page, '08b-triage-vex-draft', { dump: true })
      await page.locator('.state-opt', { hasText: 'Open' }).click() // back to a no-op draft
    }
  }
  const raBtn = page.locator('.ui-btn--ghost', { hasText: 'Risk-accept' })
  if ((await raBtn.count()) && !(await raBtn.isDisabled())) {
    await raBtn.click()
    await page.waitForSelector('.modal')
    await shot(page, '08c-risk-accept-dialog', { dump: true })
    await page.keyboard.press('Escape')
  }

  // FORCED STATE: a disagreeing finding (severity or zero-vs-nonzero surfaces differ)
  await page.goto(`${BASE}/findings?attr=disagree`)
  const hasRows = await page
    .waitForSelector('.tbl tbody tr', { timeout: 10_000 })
    .catch(() => null)
  if (hasRows) {
    await page.locator('.tbl tbody tr').first().click()
    await page.waitForSelector('.detail-head', { timeout: 10_000 })
    await page.waitForLoadState('networkidle')
    await shot(page, '09-finding-detail-disagree', { dump: true })
  } else {
    console.log('  (no disagreeing findings in this corpus — 09 skipped)')
  }

  await browser.close()
  console.log(issues.length ? `issues:\n  ${issues.join('\n  ')}` : 'issues: none')
  console.log('output:', OUT)
}

main().catch((e) => {
  console.error('FAILED:', e.message)
  process.exit(1)
})
