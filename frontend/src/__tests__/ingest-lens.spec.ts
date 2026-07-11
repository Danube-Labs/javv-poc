import { describe, expect, it } from 'vitest'
import type { BarSeriesOption } from 'echarts'

import { buildIngestLensOption } from '@/charts/buildIngestLensOption'
import type { ScanActivityData } from '@/charts/buildScanActivityOption'
import { CHART_SCANNER } from '@/styles/tokens'

const pts = (scans: number[]) =>
  scans.map((n, i) => ({ date: `2026-07-0${i + 1}T00:00:00.000Z`, scans: n }))

describe('buildIngestLensOption (compact scan-activity variant)', () => {
  const data: ScanActivityData = { trivy: pts([2, 0, 1]), grype: pts([1, 1, 0]) }

  it('keeps one bar series per scanner — never merged — with the pinned colors', () => {
    const series = buildIngestLensOption(data).series as BarSeriesOption[]
    expect(series.map((s) => s.name)).toEqual(['trivy', 'grype'])
    expect(series[0]!.data).toEqual([2, 0, 1])
    expect((series[0]!.itemStyle as { color: string }).color).toBe(CHART_SCANNER.trivy)
    expect((series[1]!.itemStyle as { color: string }).color).toBe(CHART_SCANNER.grype)
  })

  it('squeezes the frame for the strip and pins whole-run y ticks', () => {
    const option = buildIngestLensOption(data)
    expect((option.grid as { top: number }).top).toBeLessThan(12)
    expect((option.yAxis as { minInterval: number }).minInterval).toBe(1)
  })

  it('empty series → no bars (the component renders the copy instead)', () => {
    expect((buildIngestLensOption({}).series as BarSeriesOption[]).length).toBe(0)
  })
})
