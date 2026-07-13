/**
 * Approvals view-model (M9d slice 4) — pure derivations over the wire's decision rows, unit
 * tested. The queue is the ruled review surface (#30): ACTIVE risk-accepts only, soonest
 * expiry first; `expiry` is IMMUTABLE on a decision (D39 — an edit is revoke+new), so status
 * here is pure display derivation, never state.
 */

export interface ApprovalRow {
  decision_id: string
  cve_id: string
  type: string
  scope: { namespaces: string[]; images: string[] }
  apply_both_scanners: boolean
  scanner: string | null
  justification: string
  vex_justification: string | null
  expiry: string | null
  created_by: string
  created_at: string
  effective_at?: string | null
}

/** Amber window before expiry (days). Build-time `VITE_EXPIRY_WARN_DAYS`, default 7 —
 * documented in docs/CONFIGURATION.md §frontend. */
const RAW_WARN = Number(import.meta.env.VITE_EXPIRY_WARN_DAYS)
export const EXPIRY_WARN_DAYS = Number.isFinite(RAW_WARN) && RAW_WARN > 0 ? RAW_WARN : 7

export type ExpiryStatus = 'open-ended' | 'active' | 'expiring' | 'expired'

const DAY_MS = 86_400_000

/** Whole days until `expiry`, ceil'd (0 = today), measured from the display clock. */
export function daysUntil(expiry: string, nowMs: number): number {
  return Math.ceil((new Date(expiry).getTime() - nowMs) / DAY_MS)
}

/** The chip's state. `expired` acceptances are the queue's whole point — the projection
 * releases their findings back to open, and the row asks for a re-decision or cleanup. */
export function expiryStatus(
  expiry: string | null,
  nowMs: number,
  warnDays: number = EXPIRY_WARN_DAYS,
): ExpiryStatus {
  if (expiry === null) return 'open-ended'
  const ms = new Date(expiry).getTime()
  if (Number.isNaN(ms)) return 'open-ended'
  if (ms <= nowMs) return 'expired'
  return ms - nowMs <= warnDays * DAY_MS ? 'expiring' : 'active'
}

/** "cluster-wide" | "ns: a, b" | "img: nginx +2" — the D22 scope, compact. */
export function scopeLabel(scope: ApprovalRow['scope']): string {
  const ns = scope.namespaces ?? []
  const img = scope.images ?? []
  if (ns.length === 0 && img.length === 0) return 'cluster-wide'
  const parts: string[] = []
  if (ns.length > 0) parts.push(`ns: ${ns[0]}${ns.length > 1 ? ` +${ns.length - 1}` : ''}`)
  if (img.length > 0) parts.push(`img: ${img[0]}${img.length > 1 ? ` +${img.length - 1}` : ''}`)
  return parts.join(' · ')
}

/** The per-scanner subject (D22): a specific scanner, or both. */
export function scannerLabel(row: Pick<ApprovalRow, 'apply_both_scanners' | 'scanner'>): string {
  return row.apply_both_scanners || !row.scanner ? 'both' : row.scanner
}
