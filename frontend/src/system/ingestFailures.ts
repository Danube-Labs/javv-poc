/**
 * The failed-ingests read (`GET /api/v1/scanners/ingest-failures`): its query params and row
 * shape. The window is the trend vocabulary (`days` + `as_of` only at T<now), so it is built by
 * the same `buildTrendQuery` every trend lens uses — one rounding rule for "the range".
 */
import type { ScanActivityData } from '@/charts/buildScanActivityOption'
import { buildTrendQuery } from '@/charts/buildTrendQuery'

export type ScannerName = 'trivy' | 'grype'

export interface IngestFailureRow {
  '@timestamp': string
  failure_id: string
  scanner: string
  stage: string
  reason: string
  status: number
  error: string
  image_ref: string | null
}

export interface IngestFailuresPage {
  data: IngestFailureRow[]
  total: { value: number; relation: string }
  next_cursor: string | null
}

export function buildIngestFailuresQuery(p: {
  clusterId: string
  scanner: ScannerName
  windowDays: number
  t: string | null
  size: number
  cursor: string | null
}) {
  return {
    ...buildTrendQuery(p.clusterId, p.windowDays, p.t),
    scanner: p.scanner,
    size: p.size,
    ...(p.cursor === null ? {} : { cursor: p.cursor }),
  }
}

/** `GET /trends/ingest-failures`: refused pushes per bucket, one series per scanner. */
export interface FailurePoint {
  date: string
  count: number
}
export type IngestFailuresTrend = Partial<Record<ScannerName, FailurePoint[]>>

/** The trend in the shape the ingest-lens option builder draws, so both strips share one chart
 * grammar. That builder's bar value is named `scans`; here it carries the refusal count. */
export function failuresAsLensSeries(series: IngestFailuresTrend): ScanActivityData {
  const out: ScanActivityData = {}
  for (const [scanner, points] of Object.entries(series) as [ScannerName, FailurePoint[]][]) {
    out[scanner] = points.map((p) => ({ date: p.date, scans: p.count }))
  }
  return out
}

export function totalRefused(series: IngestFailuresTrend): number {
  return Object.values(series).reduce((n, points) => n + (points ?? []).reduce((m, p) => m + p.count, 0), 0)
}
