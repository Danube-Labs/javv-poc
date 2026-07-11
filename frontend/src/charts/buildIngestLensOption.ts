/** Pure option-builder: the compact ingest-lens variant of the scan-activity chart — same
 * per-scanner bars (never merged), squeezed for the strip above a data table. */
import type { EChartsOption } from 'echarts'

import { buildScanActivityOption, type ScanActivityData } from './buildScanActivityOption'

export function buildIngestLensOption(series: ScanActivityData): EChartsOption {
  const option = buildScanActivityOption(series)
  return {
    ...option,
    grid: { left: 26, right: 8, top: 6, bottom: 18 },
    // whole-run counts only — a 3-bucket axis on tiny values must not show fractions
    yAxis: { ...(option.yAxis as object), minInterval: 1, splitNumber: 2 },
  }
}
