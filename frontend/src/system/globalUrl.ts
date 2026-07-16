/**
 * The global app state ⇄ URL (restorable-state rule, audit 343; issue 433): `t` (the D28 rewind
 * point, ISO), `win` (trend-window days, fractional allowed) and `cluster` (the selected
 * cluster_id — per-browser defaults differ, so a shared link must carry the tenant explicitly)
 * ride every screen's query like filters do — a pasted link reproduces exactly what the sender
 * saw, and a reload keeps the context. T=now + the 30-day default serialize to NOTHING, so
 * everyday URLs stay clean; the cluster always serializes once selected. Pure + unit-tested;
 * the AppShell owns the wiring. (Formerly timeTravelUrl.ts — grew the cluster key.)
 */
import type { LocationQuery } from 'vue-router'

const GLOBAL_KEYS = ['t', 'win', 'cluster'] as const
const DEFAULT_WIN = 30

export function ttToQuery(t: string | null, windowDays: number): Record<string, string> {
  const q: Record<string, string> = {}
  if (t !== null) q.t = t
  // 4 decimals ≈ 9-second resolution — plenty for a trend window, keeps URLs readable
  if (windowDays !== DEFAULT_WIN) q.win = String(Math.round(windowDays * 10000) / 10000)
  return q
}

/** null = the URL carries no range at all (leave the store's defaults untouched). Garbage
 * values degrade to the defaults rather than poisoning every read. */
export function ttFromQuery(query: LocationQuery): { t: string | null; win: number } | null {
  const rawT = typeof query.t === 'string' ? query.t : null
  const rawW = typeof query.win === 'string' ? query.win : null
  if (rawT === null && rawW === null) return null
  const t = rawT !== null && Number.isFinite(Date.parse(rawT)) ? new Date(rawT).toISOString() : null
  const n = rawW !== null ? Number(rawW) : NaN
  const win = Number.isFinite(n) && n > 0 ? Math.min(365, n) : DEFAULT_WIN
  return { t, win }
}

/** The `cluster` key of a deep link, shape-checked only — whether the id EXISTS is the cluster
 * store's call (it owns the registry and the unknown-id fallback). */
export function clusterFromQuery(query: LocationQuery): string | null {
  const raw = typeof query.cluster === 'string' ? query.cluster.trim() : ''
  return raw !== '' ? raw : null
}

/** The global-key subset of a query — screens that own their query (filter sync) spread this in
 * so their `router.replace` never wipes the range or the selected cluster. */
export function keepGlobals(query: LocationQuery): Record<string, string> {
  const out: Record<string, string> = {}
  for (const k of GLOBAL_KEYS) if (typeof query[k] === 'string') out[k] = query[k]
  return out
}

/** A query minus the global keys — for comparing a screen's own params against the route. */
export function stripGlobals(query: LocationQuery): LocationQuery {
  const out = { ...query }
  for (const k of GLOBAL_KEYS) delete out[k]
  return out
}
