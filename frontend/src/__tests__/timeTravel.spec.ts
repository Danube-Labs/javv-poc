import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useTimeTravelStore } from '@/stores/timeTravel'

beforeEach(() => setActivePinia(createPinia()))

describe('timeTravel store (D28 — the T=now vs T<now branch must be observable)', () => {
  it('T=now emits NO as_of param at all', () => {
    const tt = useTimeTravelStore()
    expect(tt.isNow).toBe(true)
    expect(tt.asOfParams).toEqual({})
    expect('as_of' in tt.asOfParams).toBe(false)
  })

  it('T<now emits the explicit as_of', () => {
    const tt = useTimeTravelStore()
    tt.rewindTo('2026-07-01T00:00:00.000Z')
    expect(tt.isNow).toBe(false)
    expect(tt.asOfParams).toEqual({ as_of: '2026-07-01T00:00:00.000Z' })
  })

  it('back to now removes the param again', () => {
    const tt = useTimeTravelStore()
    tt.rewindTo('2026-07-01T00:00:00.000Z')
    tt.backToNow()
    expect(tt.asOfParams).toEqual({})
  })
})
