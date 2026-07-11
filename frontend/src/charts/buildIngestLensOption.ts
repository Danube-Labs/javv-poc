/** Pure option-builder: the compact ingest-lens variant of the scan-activity chart — same
 * per-scanner bars (never merged), squeezed for the strip above a data table. */
import type { EChartsOption } from 'echarts'

import { buildScanActivityOption, type ScanActivityData } from './buildScanActivityOption'

/** The dates axis exactly as the option builder ranks it — index-aligned with a bar click's
 * `dataIndex`, so the component can map a click back to its bucket. */
export function ingestLensDates(series: ScanActivityData): string[] {
  return (['trivy', 'grype'].map((s) => series[s as 'trivy' | 'grype']).find((r) => r?.length) ?? []).map(
    (p) => p.date,
  )
}

/** Click-to-rewind T: a day bucket maps to the END of that day (state after its ingests
 * committed, D28). A bucket still in progress means "now" — null, the caller's backToNow. */
export function bucketEndT(bucketIso: string, nowMs: number): string | null {
  const end = new Date(bucketIso).getTime() + 86_400_000 - 1
  return end >= nowMs ? null : new Date(end).toISOString()
}

export function buildIngestLensOption(series: ScanActivityData): EChartsOption {
  const option = buildScanActivityOption(series)
  return {
    ...option,
    grid: { left: 26, right: 8, top: 6, bottom: 18 },
    // whole-run counts only — a 3-bucket axis on tiny values must not show fractions
    yAxis: { ...(option.yAxis as object), minInterval: 1, splitNumber: 2 },
  }
}
