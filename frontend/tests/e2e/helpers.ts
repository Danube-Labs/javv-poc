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

export async function login(page: Page): Promise<void> {
  await walkLogin(page, BASE, USER, PASS)
}
