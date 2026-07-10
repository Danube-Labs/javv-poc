/** Pure query-builder for the two trends endpoints (M9c). The trends API is day-grained
 * (`days` int 1–365, day-floored UTC bounds server-side) — a sub-day range picker span rounds
 * UP to 1 day here, and the caller renders the daily-resolution caption (operator ruling
 * 2026-07-09, bolt README). `as_of` rides in only at T<now (D28 — omit entirely at now). */

export interface TrendQuery {
  cluster_id: string
  days: number
  as_of?: string
}

export function buildTrendQuery(clusterId: string, windowDays: number, t: string | null): TrendQuery {
  const days = Math.min(365, Math.max(1, Math.ceil(windowDays)))
  return { cluster_id: clusterId, days, ...(t === null ? {} : { as_of: t }) }
}

/** True when the picker's chosen span is finer than the chart's 1-day floor. */
export function isSubDayWindow(windowDays: number): boolean {
  return windowDays > 0 && windowDays < 1
}
