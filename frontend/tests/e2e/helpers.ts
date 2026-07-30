/**
 * Spec helpers — selectors and the login flow come from scripts/walk.mjs (the ONE owner of
 * the route matrix, testing.md §4: "a renamed selector breaks one file, loudly").
 */
import type { Page } from '@playwright/test'

// @ts-expect-error walk.mjs is the untyped shared walk module — the selector owner
import { login as walkLogin } from '../../scripts/walk.mjs'

export const BASE = process.env.JAVV_BASE ?? 'http://localhost:4173'
export const USER = process.env.JAVV_USER ?? 'admin'
export const PASS = process.env.JAVV_PASS ?? ''

/**
 * The capability-LESS viewer seeded by `development/scripts/seed-smoke.sh` (issue 460). Proving
 * a capability gate needs a session that fails it, and the admin session can never do that.
 */
export const VIEWER = process.env.JAVV_VIEWER_USER ?? 'smoke-viewer'
export const VIEWER_PASS = process.env.JAVV_VIEWER_PASS ?? 'ci-smoke-viewer-pw'

export async function login(page: Page): Promise<void> {
  await walkLogin(page, BASE, USER, PASS)
}

export async function loginViewer(page: Page): Promise<void> {
  await walkLogin(page, BASE, VIEWER, VIEWER_PASS)
}
