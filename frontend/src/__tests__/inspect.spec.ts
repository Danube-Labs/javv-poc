/**
 * Data inspector pure logic (issue 406): the rail grouping — history families collapse to one
 * summed `-*` pattern, credential indices never surface, system vs materialized split — and
 * the count/byte formatting the screen renders.
 */
import { describe, expect, it } from 'vitest'

import { fmtBytes, fmtDocs, groupIndices, totalStoreBytes } from '@/system/inspect'

const rows = [
  // real corpus names (INDEX-MAP): rollover-suffixed per-cluster append indices
  { index: 'javv-finding-occurrences-aaa-000001', 'docs.count': '1000', 'store.size': '10mb' },
  { index: 'javv-finding-occurrences-aaa-000002', 'docs.count': '2400', 'store.size': '20mb' },
  { index: 'javv-finding-occurrences-bbb-000001', 'docs.count': '600', 'store.size': '5mb' },
  { index: 'javv-images-aaa-000001', 'docs.count': '50', 'store.size': '1mb' },
  { index: 'findings', 'docs.count': '32806', 'store.size': '64mb' },
  { index: 'javv-scan-watermarks', 'docs.count': '1400', 'store.size': '2mb' },
  { index: 'system-audit-log-000001', 'docs.count': '18000', 'store.size': '8mb' },
  { index: 'system-views', 'docs.count': '12', 'store.size': '1kb' },
  // never in the rail: credential indices (backend denies them) + dot-internal
  { index: 'system-users', 'docs.count': '7', 'store.size': '1kb' },
  { index: 'system-sessions', 'docs.count': '900', 'store.size': '1mb' },
  { index: 'system-tokens', 'docs.count': '3', 'store.size': '1kb' },
  { index: '.plugins-ml-config', 'docs.count': '1', 'store.size': '1kb' },
]

describe('groupIndices', () => {
  const groups = groupIndices(rows)

  it('collapses time-partitioned families to one summed pattern', () => {
    expect(groups.history).toContainEqual({ pattern: 'javv-finding-occurrences-*', docs: 4000 })
    expect(groups.history).toContainEqual({ pattern: 'javv-images-*', docs: 50 })
    expect(groups.history).toContainEqual({ pattern: 'system-audit-log-*', docs: 18000 })
  })

  it('splits materialized state from system indices', () => {
    expect(groups.state.map((e) => e.pattern)).toEqual(['findings', 'javv-scan-watermarks'])
    expect(groups.system.map((e) => e.pattern)).toEqual(['system-views'])
  })

  it('never surfaces credential or dot-internal indices', () => {
    const all = [...groups.history, ...groups.state, ...groups.system].map((e) => e.pattern)
    for (const denied of ['system-users', 'system-sessions', 'system-tokens']) {
      expect(all).not.toContain(denied)
    }
    expect(all.some((p) => p.startsWith('.'))).toBe(false)
  })
})

describe('formatting', () => {
  it('fmtDocs compacts to the rail grammar', () => {
    expect(fmtDocs(487)).toBe('487')
    expect(fmtDocs(4363)).toBe('4.4k')
    expect(fmtDocs(28_400_000)).toBe('28.4M')
    expect(fmtDocs(1000)).toBe('1k')
  })

  it('fmtBytes renders the budget meter units', () => {
    expect(fmtBytes(612 * 1024)).toBe('612 KB')
    expect(fmtBytes(2 * 1024 * 1024)).toBe('2 MB')
    expect(fmtBytes(2.26 * 1024 ** 3)).toBe('2.3 GB')
  })

  it('totalStoreBytes sums _cat size strings', () => {
    const total = totalStoreBytes([
      { index: 'a', 'store.size': '10mb' },
      { index: 'b', 'store.size': '512kb' },
    ])
    expect(total).toBe(10 * 1024 ** 2 + 512 * 1024)
  })
})
