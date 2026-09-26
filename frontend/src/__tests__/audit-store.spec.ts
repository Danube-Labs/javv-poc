import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useAuditStore, type AuditEvent } from '@/stores/audit'

const ev = (id: string): AuditEvent =>
  ({ event_id: id, '@timestamp': '2026-09-27T10:00:00Z', actor: 'admin', action: 'login' }) as AuditEvent

const exact = (value: number) => ({ value, relation: 'eq' })

describe('audit store (cursor-stack paging)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('stores server rows/total verbatim and stacks the next cursor', () => {
    const s = useAuditStore()
    s.setResult([ev('a')], exact(812), 'cur-1')
    expect(s.rows).toHaveLength(1)
    expect(s.total).toBe(812)
    expect(s.totalIsLowerBound).toBe(false)
    expect(s.hasNext).toBe(true)
    expect(s.hasPrev).toBe(false)
    expect(s.activeCursor).toBeNull() // page 0 fetches with no cursor
  })

  it('a capped total is a lower bound, not an exact count', () => {
    const s = useAuditStore()
    s.setResult([ev('a')], { value: 10000, relation: 'gte' }, 'cur-1')
    expect(s.total).toBe(10000)
    expect(s.totalIsLowerBound).toBe(true)
  })

  it('walks next/prev over stored cursors — no offset, no jumps', () => {
    const s = useAuditStore()
    s.setResult([ev('a')], exact(100), 'cur-1')
    s.goNext()
    expect(s.page).toBe(1)
    expect(s.activeCursor).toBe('cur-1')
    s.setResult([ev('b')], exact(100), 'cur-2')
    s.goNext()
    expect(s.activeCursor).toBe('cur-2')
    s.goPrev()
    expect(s.activeCursor).toBe('cur-1')
    s.goPrev()
    expect(s.page).toBe(0)
    expect(s.activeCursor).toBeNull()
    expect(s.hasPrev).toBe(false)
  })

  it('does not advance past the last page (no next cursor)', () => {
    const s = useAuditStore()
    s.setResult([ev('a')], exact(10), null)
    s.goNext()
    expect(s.page).toBe(0)
    expect(s.hasNext).toBe(false)
  })

  it('setSize resets paging', () => {
    const s = useAuditStore()
    s.setResult([ev('a')], exact(100), 'cur-1')
    s.goNext()
    s.setSize(50)
    expect(s.size).toBe(50)
    expect(s.page).toBe(0)
    expect(s.activeCursor).toBeNull()
    expect(s.hasNext).toBe(false)
  })

  it('resetPaging goes back to page 0 and keeps the rows until the reload lands', () => {
    const s = useAuditStore()
    s.setResult([ev('a')], exact(100), 'cur-1')
    s.goNext()
    s.resetPaging()
    expect(s.page).toBe(0)
    expect(s.activeCursor).toBeNull()
    expect(s.hasNext).toBe(false)
    expect(s.rows).toHaveLength(1)
  })

  it('clearResults drops rows AND total (a cluster/T switch must not leave readable stale data)', () => {
    const s = useAuditStore()
    s.setResult([ev('a')], { value: 10000, relation: 'gte' }, 'cur-1')
    s.goNext()
    s.clearResults()
    expect(s.rows).toEqual([])
    expect(s.total).toBe(0)
    expect(s.totalIsLowerBound).toBe(false)
    expect(s.page).toBe(0)
    expect(s.activeCursor).toBeNull()
    expect(s.hasNext).toBe(false)
  })
})
