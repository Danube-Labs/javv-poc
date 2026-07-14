/**
 * The authoring-time visual rig (/visual-test, issues #301 + #387) — committed so it survives
 * sessions. Shares its route matrix + layout asserts with the CI smoke (scripts/walk.mjs);
 * what it adds over the gate is EYES: per-route screenshots + rendered-HTML dumps for the
 * impeccable anti-pattern detector, at desktop AND phone, plus the forced non-default states
 * the defaults-only walk can't reach (the history banner once hid an AA failure).
 *
 *   JAVV_USER=admin JAVV_PASS=… node scripts/visual-capture.mjs [outDir]
 *   node ../.claude/skills/impeccable/scripts/detect.mjs <outDir>/*.html
 *
 * Exit: 1 on console/page errors or DESKTOP layout violations (same law as CI). Phone layout
 * findings are WARN-ONLY by ruling (#387): no phone layout exists yet — flip them gating
 * when a responsive pass lands. Phone screenshots are captured for authoring regardless.
 *
 * Notes for agents: kill the node child by PID/port, never `pkill -f`; the SPA answers 200
 * HTML for any GET — verify proxied responses by body; viewport is set before any navigation.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { chromium } from 'playwright'

import { VIEWPORTS, ROUTES, collectPageIssues, layoutIssues, login, clickDetail } from './walk.mjs'

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

const issues = [] // gating: console/pageerror + desktop layout
const warnings = [] // phone layout (warn-only until a responsive pass exists)
const pad = (n) => String(n).padStart(2, '0')

async function shot(page, name, { dump = false, clip } = {}) {
  await page.screenshot({ path: `${OUT}/${name}.png`, ...(clip ? { clip } : {}) })
  if (dump) writeFileSync(`${OUT}/${name}.html`, await page.content())
  console.log('  captured', name + (dump ? ' (+html dump)' : ''))
}

/** The full matrix: every route, screenshot + dump + layout asserts, at one viewport. */
async function walkAndCapture(page, vpName) {
  const sink = vpName === 'phone' ? warnings : issues
  let n = 10 // numbered so the output dir reads in walk order
  for (const route of ROUTES) {
    await page.goto(`${BASE}${route.path}`)
    const ready = await page.waitForSelector(route.ready, { timeout: 15_000 }).catch(() => null)
    if (!ready) {
      issues.push(`[route ${route.name} ${vpName}] never became ready (${route.ready})`)
      continue
    }
    await page.waitForLoadState('networkidle')
    sink.push(...(await layoutIssues(page, `${route.name} ${vpName}`)))
    await shot(page, `${n++}-${route.name}-${vpName}`, { dump: vpName === 'desktop' })
    await page.waitForTimeout(250)
  }
  // the two row-click details
  await clickDetail(page, BASE, '/findings', '.detail-head', `finding-detail ${vpName}`, sink)
  await shot(page, `${n++}-finding-detail-${vpName}`, { dump: vpName === 'desktop' })
  await clickDetail(page, BASE, '/images', '.back-btn', `image-detail ${vpName}`, sink)
  await shot(page, `${n++}-image-detail-${vpName}`, { dump: vpName === 'desktop' })
}

/** Forced non-default states (desktop only — deep interactions stay out of the phone pass). */
async function forcedStates(page) {
  await page.goto(`${BASE}/findings`)
  await page.waitForSelector('.tbl tbody tr', { timeout: 15_000 })

  // filtered (pills + URL sync)
  await page.locator('.facet-row', { hasText: 'critical' }).first().click()
  await page.waitForTimeout(700)
  await shot(page, '40-findings-filtered', { dump: true })
  await page.locator('.clear-all').click()
  await page.waitForTimeout(400)

  // time menu open
  await page.click('.time-range')
  await page.waitForSelector('.time-menu')
  await shot(page, '41-time-menu', { clip: { x: 240, y: 0, width: 1400, height: 560 } })

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
  await shot(page, '42-history-state', { dump: true })
  await page.click('.time-range')
  await page.locator('.back-now').click()
  await page.waitForTimeout(400)

  // columns menu open
  await page.locator('.cols-dd .ui-btn').click()
  await page.waitForSelector('.cols-menu')
  await shot(page, '43-columns-menu')
  await page.keyboard.press('Escape')

  // export + bulk dialogs (slice 4) — DRAFT ONLY, never submitted
  await page.locator('.export-wrap .ui-btn').click()
  await page.waitForSelector('.modal')
  await shot(page, '44-export-dialog', { dump: true })
  await page.keyboard.press('Escape')
  await page.locator('.facet-row', { hasText: 'critical' }).first().click()
  await page.waitForTimeout(600)
  if (await page.locator('.bulk-wrap .ui-btn').count()) {
    await page.locator('.bulk-wrap .ui-btn').click()
    await page.waitForSelector('.modal')
    await shot(page, '45-bulk-dialog', { dump: true })
    await page.keyboard.press('Escape')
  } else {
    console.log('  (bulk hidden — principal lacks can_triage: RBAC state captured implicitly)')
  }
  await page.locator('.clear-all').click()
  await page.waitForTimeout(500)

  // FORCED STATE: triage draft (vex chips) + risk-accept dialog — DRAFT ONLY, never saved:
  // mutations in automated visual runs are confirmation-gated (standing rule).
  // Fresh navigation first: clicking mid-refetch after clear-all lands on a detaching row.
  await page.goto(`${BASE}/findings`)
  await page.waitForSelector('.tbl tbody tr', { timeout: 15_000 })
  await page.waitForLoadState('networkidle')
  await page.locator('.tbl tbody tr td').first().click()
  await page.waitForSelector('.detail-head', { timeout: 15_000 })
  await page.waitForLoadState('networkidle')
  const naBtn = page.locator('.state-opt', { hasText: 'Not affected' })
  if (await naBtn.count()) {
    if (await naBtn.isDisabled()) {
      // a viewer principal: the locked panel IS the forced state worth capturing
      await shot(page, '46-triage-locked', { dump: true })
    } else {
      await naBtn.click()
      await page.waitForSelector('.vex-chips')
      await shot(page, '46-triage-vex-draft', { dump: true })
      await page.locator('.state-opt', { hasText: 'Open' }).click() // back to a no-op draft
    }
  }
  const raBtn = page.locator('.ui-btn--ghost', { hasText: 'Risk-accept' })
  if ((await raBtn.count()) && !(await raBtn.isDisabled())) {
    await raBtn.click()
    await page.waitForSelector('.modal')
    await shot(page, '47-risk-accept-dialog', { dump: true })
    await page.keyboard.press('Escape')
  }

  // FORCED STATE: a disagreeing finding (severity or zero-vs-nonzero surfaces differ)
  await page.goto(`${BASE}/findings?attr=disagree`)
  const hasRows = await page.waitForSelector('.tbl tbody tr', { timeout: 10_000 }).catch(() => null)
  if (hasRows) {
    await page.locator('.tbl tbody tr td').first().click()
    await page.waitForSelector('.detail-head', { timeout: 10_000 })
    await page.waitForLoadState('networkidle')
    await shot(page, '48-finding-detail-disagree', { dump: true })
  } else {
    console.log('  (no disagreeing findings in this corpus — 48 skipped)')
  }
}

async function main() {
  mkdirSync(OUT, { recursive: true })
  const browser = await chromium.launch({ headless: true })

  for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
    console.log(`— ${vpName} (${viewport.width}×${viewport.height})`)
    const page = await browser.newPage({ viewport })
    // pre-login state first (the boot /auth/me 401 is by design — not collected as an issue)
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
    await shot(page, `01-login-${vpName}`, { dump: vpName === 'desktop' })
    await login(page, BASE, USER, PASS)
    collectPageIssues(page, issues)
    await walkAndCapture(page, vpName)
    if (vpName === 'desktop') await forcedStates(page)
    await page.close()
  }

  await browser.close()
  if (warnings.length) console.log(`phone layout warnings (non-gating, #387 ruling):\n  ${warnings.join('\n  ')}`)
  console.log('output:', OUT)
  if (issues.length) {
    console.error(`ISSUES (gating):\n  ${issues.join('\n  ')}`)
    process.exit(1)
  }
  console.log('issues: none')
}

main().catch((e) => {
  console.error('FAILED:', e.message)
  process.exit(1)
})
