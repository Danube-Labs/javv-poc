import { describe, expect, it } from 'vitest'
import type { LineSeriesOption } from 'echarts'

import { buildFindingsTrendOption, type FindingsTrendData } from '@/charts/buildFindingsTrendOption'
import { buildPtypeDonutOption } from '@/charts/buildPtypeDonutOption'
import { buildScanActivityOption } from '@/charts/buildScanActivityOption'
import { buildTrendQuery, isSubDayWindow } from '@/charts/buildTrendQuery'
import { CHART_PTYPE_RAMP, CHART_SCANNER } from '@/styles/tokens'

const pts = (counts: number[]) =>
  counts.map((count, i) => ({ date: `2026-07-0${i + 1}T00:00:00.000Z`, count }))

describe('buildTrendQuery (pure params contract)', () => {
  it('emits cluster + clamped integer days; as_of only at T<now (D28)', () => {
    expect(buildTrendQuery('c-1', 30, null)).toEqual({ cluster_id: 'c-1', days: 30 })
    expect(buildTrendQuery('c-1', 30, '2026-07-01T00:00:00Z')).toEqual({
      cluster_id: 'c-1',
      days: 30,
      as_of: '2026-07-01T00:00:00Z',
    })
  })

  it('sub-day spans round UP to 1 day (day-grained API, operator ruling)', () => {
    expect(buildTrendQuery('c-1', 0.0625, null).days).toBe(1) // "last 90 minutes"
    expect(isSubDayWindow(0.0625)).toBe(true)
    expect(isSubDayWindow(30)).toBe(false)
  })

  it('clamps to the API bounds 1–365', () => {
    expect(buildTrendQuery('c-1', 900, null).days).toBe(365)
    expect(buildTrendQuery('c-1', 0, null).days).toBe(1)
  })
})

describe('buildFindingsTrendOption (per-scanner sacred)', () => {
  const data: FindingsTrendData = {
    new: { trivy: pts([1, 2, 3]), grype: pts([4, 5, 6]) },
    resolved: { grype: pts([0, 1, 0]) },
  }

  it('emits one series per (kind, scanner) — never a merged series', () => {
    const series = buildFindingsTrendOption(data).series as LineSeriesOption[]
    expect(series.map((s) => s.name)).toEqual([
      'new · trivy',
      'new · grype',
      'resolved (scan-observed) · grype',
    ])
    // the counts pass through verbatim — no client math
    expect(series[0]!.data).toEqual([1, 2, 3])
    expect(series[1]!.data).toEqual([4, 5, 6])
  })

  it('series colors are the pinned scanner literals; resolved is dashed + labeled scan-observed', () => {
    const series = buildFindingsTrendOption(data).series as LineSeriesOption[]
    expect(series[0]!.lineStyle?.color).toBe(CHART_SCANNER.trivy)
    expect(series[1]!.lineStyle?.color).toBe(CHART_SCANNER.grype)
    expect(series[2]!.lineStyle?.type).toBe('dashed')
    expect(String(series[2]!.name)).toContain('scan-observed')
  })
})

describe('buildScanActivityOption', () => {
  it('one bar series per scanner with verbatim counts', () => {
    const opt = buildScanActivityOption({
      trivy: [{ date: '2026-07-01T00:00:00.000Z', scans: 2 }],
      grype: [{ date: '2026-07-01T00:00:00.000Z', scans: 1 }],
    })
    const series = opt.series as { name?: string; data?: unknown }[]
    expect(series.map((s) => s.name)).toEqual(['trivy', 'grype'])
    expect(series[0]!.data).toEqual([2])
  })
})

describe('buildPtypeDonutOption', () => {
  it('maps buckets onto the teal ramp verbatim', () => {
    const opt = buildPtypeDonutOption([
      { key: 'os', count: 1885 },
      { key: 'deb', count: 1783 },
    ])
    const pie = (opt.series as { data: { name: string; value: number; itemStyle: { color: string } }[] }[])[0]!
    expect(pie.data.map((d) => [d.name, d.value])).toEqual([
      ['os', 1885],
      ['deb', 1783],
    ])
    expect(pie.data[0]!.itemStyle.color).toBe(CHART_PTYPE_RAMP[0])
  })
})

describe('buildSeverityTrendOption (the 1b severity lens)', () => {
  it('one line per canonical bucket in rank order, colored from the pinned severity map', async () => {
    const { buildSeverityTrendOption } = await import('@/charts/buildSeverityTrendOption')
    const { CHART_SEV } = await import('@/styles/tokens')
    const opt = buildSeverityTrendOption({
      high: pts([2, 1, 0]),
      critical: pts([1, 0, 0]),
    })
    const series = opt.series as LineSeriesOption[]
    expect(series.map((s) => s.name)).toEqual(['critical', 'high']) // rank order, empties dropped
    expect(series[0]!.lineStyle?.color).toBe(CHART_SEV.critical)
    expect(series[0]!.data).toEqual([1, 0, 0]) // verbatim server counts
  })
})
