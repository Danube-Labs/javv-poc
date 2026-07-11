import { describe, expect, it } from 'vitest'
import type { BarSeriesOption } from 'echarts'

import {
  bucketEndT,
  buildIngestLensOption,
  ingestInterval,
  ingestLensDates,
} from '@/charts/buildIngestLensOption'
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

describe('click-to-rewind mapping (D28: a day bucket → the whole-app T)', () => {
  it('dataIndex maps through the same date axis the bars use', () => {
    expect(ingestLensDates({ trivy: pts([2, 0, 1]) })).toEqual([
      '2026-07-01T00:00:00.000Z',
      '2026-07-02T00:00:00.000Z',
      '2026-07-03T00:00:00.000Z',
    ])
    // trivy absent → grype rows carry the axis
    expect(ingestLensDates({ grype: pts([1]) })).toEqual(['2026-07-01T00:00:00.000Z'])
  })

  it('a finished day rewinds to its END; a day still in progress is "now" (null)', () => {
    const nowMs = Date.parse('2026-07-10T12:00:00Z')
    expect(bucketEndT('2026-07-08T00:00:00.000Z', nowMs)).toBe('2026-07-08T23:59:59.999Z')
    expect(bucketEndT('2026-07-10T00:00:00.000Z', nowMs)).toBeNull()
  })

  it('hourly buckets rewind to the hour end (the 4-hour-cadence lens, audit 343)', () => {
    const nowMs = Date.parse('2026-07-10T12:30:00Z')
    expect(bucketEndT('2026-07-10T08:00:00.000Z', nowMs, 'hour')).toBe('2026-07-10T08:59:59.999Z')
    expect(bucketEndT('2026-07-10T12:00:00.000Z', nowMs, 'hour')).toBeNull()
  })
})

describe('ingestInterval (short live ranges bucket hourly)', () => {
  it('≤2 days at T=now → hour; longer or past T → day', () => {
    expect(ingestInterval(1, null)).toBe('hour')
    expect(ingestInterval(0.02, null)).toBe('hour')
    expect(ingestInterval(2, null)).toBe('hour')
    expect(ingestInterval(30, null)).toBe('day')
    expect(ingestInterval(1, '2026-07-08T00:00:00Z')).toBe('day') // the reader is daily-only
  })

  it('hourly option relabels the axis in HH:mm', () => {
    const series = { trivy: [{ date: '2026-07-10T08:00:00.000Z', scans: 2 }] }
    const opt = buildIngestLensOption(series, 'hour')
    expect((opt.xAxis as { data: string[] }).data.every((l) => /^\d{2}:\d{2}$/.test(l))).toBe(true)
  })
})
