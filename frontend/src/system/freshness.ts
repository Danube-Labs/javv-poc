/** Pure view-model for the D20 freshness banner — filter + labels, unit-tested. */

export interface FreshnessRow {
  scanner: string
  last_ingest_at: string | null
  silent_for_seconds: number | null
}

/** The D20 seed default (N = 3 days) — mirrors the backend's `StalenessTimers` default. Only a
 * fallback while the live read is in flight: callers thread the cluster's EFFECTIVE window from
 * `stores/staleness` (the settings panel edits it at runtime, so build-time settings would be wrong). */
export const D20_FRESHNESS_DEFAULT_S = 3 * 24 * 3600

/** Cluster-grade freshness status: ok / stale (any scanner silent past the D20 threshold) /
 * none (no scanner has EVER ingested — first sweep pending, distinct from stale). */
export function freshnessStatus(
  rows: FreshnessRow[],
  thresholdS: number = D20_FRESHNESS_DEFAULT_S,
): 'ok' | 'stale' | 'none' {
  const seen = rows.filter((r) => r.last_ingest_at !== null)
  if (seen.length === 0) return 'none'
  return seen.some((r) => (r.silent_for_seconds ?? 0) > thresholdS) ? 'stale' : 'ok'
}

export function silentRows(
  rows: FreshnessRow[],
  thresholdS: number = D20_FRESHNESS_DEFAULT_S,
): FreshnessRow[] {
  return rows.filter((r) => (r.silent_for_seconds ?? 0) > thresholdS)
}

/**
 * What the banner knows (issue 651: a failed read is never silent): nothing yet, a current good
 * read, a failed read with nothing known before it, or the last good read kept after a later
 * read failed. Kept rows still drive the banner; they are just no longer current.
 */
export type FreshnessCheck =
  | { kind: 'pending' }
  | { kind: 'ok'; rows: FreshnessRow[]; checkedAt: number }
  | { kind: 'failed' }
  | { kind: 'outdated'; rows: FreshnessRow[]; checkedAt: number }

/** The next state after one read: `read` is the good answer, or null when the read failed. */
export function nextFreshnessCheck(
  prev: FreshnessCheck,
  read: { rows: FreshnessRow[]; at: number } | null,
): FreshnessCheck {
  if (read) return { kind: 'ok', rows: read.rows, checkedAt: read.at }
  if (prev.kind === 'ok' || prev.kind === 'outdated') return { ...prev, kind: 'outdated' }
  return { kind: 'failed' }
}

export function checkRows(check: FreshnessCheck): FreshnessRow[] {
  return check.kind === 'ok' || check.kind === 'outdated' ? check.rows : []
}

/** Vuln-DB age flag (M9d slice 2): a running scanner with a stale database quietly under-reports
 * — flag `scanner_db_built` older than `VITE_DB_AGE_WARN_DAYS` (build-time; default 7: both
 * scanners refresh their DBs daily, a week behind is a real smell). */
const DB_DAYS = Number(import.meta.env.VITE_DB_AGE_WARN_DAYS)
export const DB_AGE_WARN_AFTER_S =
  Number.isFinite(DB_DAYS) && DB_DAYS > 0 ? DB_DAYS * 86_400 : 7 * 86_400

export function dbAgeSeconds(builtIso: string | null, nowMs: number = Date.now()): number | null {
  if (!builtIso) return null
  const built = Date.parse(builtIso)
  return Number.isFinite(built) ? Math.max(0, (nowMs - built) / 1000) : null
}

/** "4 days" / "1 day" / "26 hours" — the urgency number, coarse on purpose. */
export function silentFor(seconds: number | null): string {
  const s = seconds ?? 0
  const days = Math.floor(s / 86_400)
  if (days >= 1) return `${days} day${days === 1 ? '' : 's'}`
  return `${Math.floor(s / 3600)} hours`
}

/** 24h, app-wide fmtAt convention — never locale-default AM/PM. */
export function lastDataAt(iso: string | null): string {
  if (!iso) return 'never'
  return new Date(iso).toLocaleString('en-GB', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}
