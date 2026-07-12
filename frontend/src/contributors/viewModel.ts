/** Pure view-model for the Contributors screen (M9d slice 3) — presentation derivations over
 * the `/contributors` wire (leaderboard rows + the team `totals` block), unit-tested. Every
 * NUMBER is the server's; these helpers only order, label, and format. */

import { CHART_PTYPE_RAMP } from '@/styles/tokens'

export interface BoardRow {
  actor: string
  actions: number
  by_action: Record<string, number>
  handled: number
  median_ttr_seconds: number | null
  sla_hit_pct: number | null
}

export interface TeamTotals {
  actions: number
  by_action: Record<string, number>
  handled: number
  median_ttr_seconds: number | null
  sla_hit_pct: number | null
  critical_cleared: number
}

export const resolvedOf = (r: BoardRow): number => r.by_action['resolve'] ?? 0
export const ackOf = (r: BoardRow): number => r.by_action['acknowledge'] ?? 0

/** Prototype order: most findings resolved; ties fall back to handled, then total actions,
 * then the name — deterministic so the podium can't flicker between equal contributors. */
export function sortBoard(rows: BoardRow[]): BoardRow[] {
  return [...rows].sort(
    (a, b) =>
      resolvedOf(b) - resolvedOf(a) ||
      b.handled - a.handled ||
      b.actions - a.actions ||
      a.actor.localeCompare(b.actor),
  )
}

/** "AB" from a username — first letters of the first two word-ish parts, else the first two
 * characters ("dragos.daniel" → DD, "admin" → AD). Presentation only; the wire has no names. */
export function initials(actor: string): string {
  const parts = actor.split(/[^a-zA-Z0-9]+/).filter(Boolean)
  const two =
    parts.length >= 2 ? `${parts[0]![0]}${parts[1]![0]}` : (parts[0] ?? actor).slice(0, 2)
  return two.toUpperCase()
}

/** Deterministic decorative tone per actor — the sanctioned categorical ramp (tokens.ts),
 * never severity/scanner hexes. Same actor, same color, everywhere on the screen. */
export function actorTone(actor: string): string {
  let h = 0
  for (let i = 0; i < actor.length; i++) h = (h * 31 + actor.charCodeAt(i)) >>> 0
  return CHART_PTYPE_RAMP[h % CHART_PTYPE_RAMP.length]!
}

/** "1.5d" / "18h" / "<1h" / "—" — the median-TTR cell, coarse on purpose. */
export function fmtMedian(seconds: number | null): string {
  if (seconds === null) return '—'
  const days = seconds / 86_400
  if (days >= 1) {
    const d = Math.round(days * 10) / 10
    return `${Number.isInteger(d) ? d.toFixed(0) : d}d`
  }
  const hours = Math.floor(seconds / 3_600)
  return hours >= 1 ? `${hours}h` : '<1h'
}

/** Prototype SLA tiers: ≥88 good · ≥80 ok · else low; null = no SLA-bearing sample. */
export function slaTier(pct: number | null): 'good' | 'ok' | 'low' | null {
  if (pct === null) return null
  return pct >= 88 ? 'good' : pct >= 80 ? 'ok' : 'low'
}

/** The trend window → the endpoint's `days` (int, 1..365): Last 24h → 1. */
export function daysFromWindow(windowDays: number): number {
  return Math.min(365, Math.max(1, Math.ceil(windowDays)))
}
