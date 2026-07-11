import { describe, expect, it } from 'vitest'

import { buildImageAtTQuery } from '@/images/buildImageAtTQuery'
import { digestEras, notYetScannedAt, type TimelineEvent } from '@/images/subTimeline'

describe('buildImageAtTQuery (the M8b two-step, D38/H6)', () => {
  it('emits TWO DISTINCT queries — inventory has no digest/scanner, vulns has both; never merged', () => {
    const q = buildImageAtTQuery('c-1', 'sha256:abc', 'trivy', '2026-07-01T00:00:00Z')
    expect(q.runtime_inventory_at_T).toEqual({ cluster_id: 'c-1', as_of: '2026-07-01T00:00:00Z' })
    expect(q.vulns_as_scanned_at_T).toEqual({
      cluster_id: 'c-1',
      image_digest: 'sha256:abc',
      scanner: 'trivy',
      as_of: '2026-07-01T00:00:00Z',
    })
    expect(Object.keys(q)).toEqual(['runtime_inventory_at_T', 'vulns_as_scanned_at_T'])
    expect(q.runtime_inventory_at_T).not.toBe(q.vulns_as_scanned_at_T)
  })

  it('T=now omits as_of ENTIRELY in both — the branch is observable in the params', () => {
    const q = buildImageAtTQuery('c-1', 'sha256:abc', 'grype', null)
    expect('as_of' in q.runtime_inventory_at_T).toBe(false)
    expect('as_of' in q.vulns_as_scanned_at_T).toBe(false)
  })
})

const ev = (order: number, scanner: string, digest: string, ts: string, total = 1): TimelineEvent => ({
  scan_order: order,
  scanner,
  image_digest: digest,
  '@timestamp': ts,
  total,
})

describe('digestEras (the sub-timeline view-model)', () => {
  const events = [
    ev(1, 'trivy', 'sha256:v1', '2026-07-01T00:00:00Z', 5),
    ev(1, 'grype', 'sha256:v1', '2026-07-01T00:01:00Z', 7),
    ev(2, 'trivy', 'sha256:v1', '2026-07-02T00:00:00Z', 4),
    // trivy order 3 missing = a GAP; build changed to v2 by order 4
    ev(4, 'trivy', 'sha256:v2', '2026-07-04T00:00:00Z', 0),
  ]

  it('one scanner only (per-scanner sacred), eras split on digest change, gaps marked', () => {
    const eras = digestEras(events, 'trivy')
    expect(eras).toHaveLength(2)
    expect(eras[0]).toMatchObject({ digest: 'sha256:v1', runs: 2, totalAtLast: 4, gapBefore: false })
    expect(eras[1]).toMatchObject({ digest: 'sha256:v2', runs: 1, totalAtLast: 0, gapBefore: true })
    // grype's event never leaks into trivy's timeline
    expect(digestEras(events, 'grype')).toHaveLength(1)
  })

  it('a gap WITHOUT a digest change still starts a new era (never a silent gap)', () => {
    const eras = digestEras(
      [ev(1, 'trivy', 'sha256:v1', '2026-07-01T00:00:00Z'), ev(3, 'trivy', 'sha256:v1', '2026-07-03T00:00:00Z')],
      'trivy',
    )
    expect(eras).toHaveLength(2)
    expect(eras[1]!.gapBefore).toBe(true)
  })

  it('notYetScannedAt: T before the scanner’s first committed event — or no events at all', () => {
    expect(notYetScannedAt(events, 'trivy', '2026-06-30T00:00:00Z')).toBe(true)
    expect(notYetScannedAt(events, 'trivy', '2026-07-02T12:00:00Z')).toBe(false)
    expect(notYetScannedAt(events, 'trivy', null)).toBe(false)
    expect(notYetScannedAt([], 'trivy', '2026-07-02T00:00:00Z')).toBe(true)
  })
})
