import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useToastStore } from '@/stores/toast'

describe('toast store (the app-wide confirmation channel)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })
  afterEach(() => vi.useRealTimers())

  it('pushes and auto-dismisses after the kind timeout', () => {
    const s = useToastStore()
    s.success('Triage saved')
    expect(s.toasts).toHaveLength(1)
    expect(s.toasts[0]).toMatchObject({ kind: 'success', message: 'Triage saved' })
    vi.advanceTimersByTime(4000)
    expect(s.toasts).toHaveLength(0)
  })

  it('errors linger longer than successes', () => {
    const s = useToastStore()
    s.success('ok')
    s.error('boom')
    vi.advanceTimersByTime(4000)
    expect(s.toasts.map((t) => t.kind)).toEqual(['error'])
    vi.advanceTimersByTime(4000)
    expect(s.toasts).toHaveLength(0)
  })

  it('manual dismiss removes the toast and its timer', () => {
    const s = useToastStore()
    const id = s.info('fyi')
    s.dismiss(id)
    expect(s.toasts).toHaveLength(0)
    vi.advanceTimersByTime(10_000) // the cleared timer must not throw or resurrect anything
    expect(s.toasts).toHaveLength(0)
  })

  it('caps the stack — oldest drops first', () => {
    const s = useToastStore()
    for (let i = 1; i <= 6; i++) s.success(`m${i}`)
    expect(s.toasts.map((t) => t.message)).toEqual(['m3', 'm4', 'm5', 'm6'])
  })
})
