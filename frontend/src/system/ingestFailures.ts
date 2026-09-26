/**
 * The failed-ingests read (`GET /api/v1/scanners/ingest-failures`): its query params and row
 * shape. The window is the trend vocabulary (`days` + `as_of` only at T<now), so it is built by
 * the same `buildTrendQuery` every trend lens uses — one rounding rule for "the range".
 */
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
