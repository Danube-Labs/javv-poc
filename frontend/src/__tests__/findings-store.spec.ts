import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useFindingsStore, type FindingRow } from '@/stores/findings'

const row = (key: string): FindingRow =>
  ({ finding_key: key, cve_id: 'CVE-1', scanner: 'trivy' }) as unknown as FindingRow

describe('findings store (cursor-stack paging)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('stores server rows/total verbatim and stacks the next cursor', () => {
    const s = useFindingsStore()
    s.setResult([row('a')], 4291, 'cur-1')
    expect(s.rows).toHaveLength(1)
    expect(s.total).toBe(4291)
    expect(s.hasNext).toBe(true)
    expect(s.hasPrev).toBe(false)
    expect(s.activeCursor).toBeNull() // page 0 fetches with no cursor
  })

  it('walks next/prev over stored cursors — no offset, no jumps', () => {
    const s = useFindingsStore()
    s.setResult([row('a')], 100, 'cur-1')
    s.goNext()
    expect(s.page).toBe(1)
    expect(s.activeCursor).toBe('cur-1')
    s.setResult([row('b')], 100, 'cur-2')
    s.goNext()
    expect(s.activeCursor).toBe('cur-2')
    s.goPrev()
    s.goPrev()
    expect(s.page).toBe(0)
    expect(s.activeCursor).toBeNull()
    expect(s.hasPrev).toBe(false)
  })

  it('does not advance past the last page (no next cursor)', () => {
    const s = useFindingsStore()
    s.setResult([row('a')], 10, null)
    s.goNext()
    expect(s.page).toBe(0)
    expect(s.hasNext).toBe(false)
  })

  it('sort toggles direction on the same column, desc on a new one, and resets paging', () => {
    const s = useFindingsStore()
    s.setResult([row('a')], 100, 'cur-1')
    s.goNext()
    s.setSort('severity_rank') // same as default → toggles desc→asc
    expect(s.order).toBe('asc')
    expect(s.page).toBe(0)
    expect(s.cursors).toEqual([null])
    s.setSort('cvss') // new column → desc
    expect(s.sort).toBe('cvss')
    expect(s.order).toBe('desc')
  })

  it('setSize resets paging', () => {
    const s = useFindingsStore()
    s.setResult([row('a')], 100, 'cur-1')
    s.goNext()
    s.setSize(50)
    expect(s.size).toBe(50)
    expect(s.page).toBe(0)
    expect(s.nextCursor).toBeNull()
  })

  it('clearResults drops rows AND total (a cluster/T switch must not leave readable stale data)', () => {
    const s = useFindingsStore()
    s.setResult([row('a')], 4291, 'cur-1')
    s.goNext()
    s.clearResults()
    expect(s.rows).toEqual([])
    expect(s.total).toBe(0)
    expect(s.page).toBe(0)
    expect(s.cursors).toEqual([null])
    expect(s.nextCursor).toBeNull()
  })
})
