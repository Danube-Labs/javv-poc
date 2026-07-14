/**
 * The CI route smoke (#383, testing.md §4): a built frontend + a fixture-seeded backend,
 * walked headless at the desktop viewport through the shared matrix (scripts/walk.mjs).
 * Desktop-only BY RULING (#387): the app has no phone layout yet — phone runs live in the
 * authoring rig (visual-capture.mjs) as screenshots, and start gating here once a
 * responsive pass exists. Gating asserts — any of these fails the job:
 *   - every route renders its data-ready selector (not just the shell);
 *   - zero console.error / pageerror anywhere in the walk;
 *   - layout sanity per route (no horizontal scroll, no off-viewport bleed, no sibling overlap);
 *   - server-side-everything: the findings grid got its rows from a backend query;
 *   - with --core-loop (CI sets it; keep local runs read-only): a triage action persists
 *     across a reload, then is reverted (the store is left as found).
 *
 *   JAVV_BASE=http://localhost:4173 JAVV_USER=… JAVV_PASS=… node scripts/ci-smoke.mjs [--core-loop]
 *
 * Deliberately shallow: dialogs, forced states and screenshots live in the authoring rig
 * (visual-capture.mjs), which imports the same walk — keep deep interactions out of the gate.
 */
import { chromium } from 'playwright'

import { VIEWPORTS, collectPageIssues, walkRoutes, clickDetail, login } from './walk.mjs'

const BASE = process.env.JAVV_BASE ?? 'http://localhost:4173'
const USER = process.env.JAVV_USER
const PASS = process.env.JAVV_PASS
const CORE_LOOP = process.argv.includes('--core-loop')
if (!USER || !PASS) {
  console.error('set JAVV_USER and JAVV_PASS')
  process.exit(2)
}

async function coreLoop(page, issues) {
  // open the first finding, acknowledge it, prove it survives a reload, put it back.
  // Every step is caught and named — a failed write must report WHAT failed, and the
  // revert only runs when the write actually landed (a no-op draft disables Save).
  const patches = []
  page.on('response', (r) => {
    if (r.request().method() === 'PATCH' && r.url().includes('/api/v1/findings')) {
      patches.push(`${r.status()} ${r.url()}`)
    }
  })
  const ok = await clickDetail(page, BASE, '/findings', '.detail-head', 'finding-core-loop', issues)
  if (!ok) return
  const url = page.url()
  const ack = page.locator('.state-opt', { hasText: 'Acknowledge' })
  const open = page.locator('.state-opt', { hasText: 'Open' })
  const save = page.locator('button', { hasText: 'Save to audit trail' })
  if (!(await ack.count()) || (await ack.isDisabled())) {
    issues.push('[core-loop] triage panel absent or not actionable for this principal')
    return
  }
  const isOn = async (loc) => ((await loc.getAttribute('class')) ?? '').includes('state-opt-on')
  const step = async (name, fn) => {
    try {
      await fn()
      return true
    } catch (e) {
      issues.push(`[core-loop] ${name}: ${e.message.split('\n')[0]} (PATCHes so far: ${patches.join(' · ') || 'none'})`)
      return false
    }
  }

  const wasAcked = await isOn(ack)
  if (!(await step('select state', () => (wasAcked ? open : ack).click({ timeout: 10_000 })))) return
  if (!(await step('save', () => save.click({ timeout: 10_000 })))) return
  await page.waitForLoadState('networkidle')
  // the reload re-READS the findings index, which refreshes ~1s behind the write (the live
  // UI never sees this — it applies the PATCH response client-side). Poll, don't assert once.
  let persisted = false
  for (let attempt = 0; attempt < 4 && !persisted; attempt++) {
    if (attempt > 0) await page.waitForTimeout(1_000)
    await page.goto(url)
    await page.waitForSelector('.detail-head', { timeout: 15_000 })
    await page.waitForLoadState('networkidle')
    persisted = (await isOn(ack)) !== wasAcked
  }
  if (!persisted) {
    issues.push(`[core-loop] triage action did not persist across reload (PATCHes: ${patches.join(' · ') || 'none'})`)
    return // nothing landed — nothing to revert
  }
  // revert — leave the store as found
  await step('revert select', () => (wasAcked ? ack : open).click({ timeout: 10_000 }))
  await step('revert save', () => save.click({ timeout: 10_000 }))
  await page.waitForLoadState('networkidle')
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const issues = []

  const page = await browser.newPage({ viewport: VIEWPORTS.desktop })

  // server-side-everything: rows must come from a backend search, not client math
  let findingsQueried = false
  page.on('request', (r) => {
    if (r.url().includes('/api/v1/findings')) findingsQueried = true
  })

  await login(page, BASE, USER, PASS).catch((e) => issues.push(`[login] ${e.message}`))
  // errors collected only post-login: the boot-time /auth/me session probe 401s by design
  // on a fresh browser, and the browser logs every non-2xx as console.error
  collectPageIssues(page, issues)
  await walkRoutes(page, BASE, issues)
  if (!findingsQueried) issues.push('[desktop] findings grid rendered without a backend query')

  await clickDetail(page, BASE, '/findings', '.detail-head', 'finding-detail', issues)
  await clickDetail(page, BASE, '/images', '.back-btn', 'image-detail', issues)
  if (CORE_LOOP) await coreLoop(page, issues)

  await browser.close()
  if (issues.length) {
    console.error(`SMOKE FAILED — ${issues.length} issue(s):\n  ${issues.join('\n  ')}`)
    process.exit(1)
  }
  console.log('smoke: all routes clean (desktop)')
}

main().catch((e) => {
  console.error('FAILED:', e.message)
  process.exit(1)
})
