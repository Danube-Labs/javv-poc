import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useApi } from '@/composables/useApi'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'

beforeEach(() => setActivePinia(createPinia()))

describe('useApi.withGlobals — the tenant + rewind injector', () => {
  it('always injects the selected cluster_id (D38/H9 chokepoint)', () => {
    useClusterStore().selectedId = 'c-1'
    expect(useApi().withGlobals({ size: 25 })).toEqual({ size: 25, cluster_id: 'c-1' })
  })

  it('injects as_of only when time-traveling', () => {
    useClusterStore().selectedId = 'c-1'
    const tt = useTimeTravelStore()
    tt.rewindTo('2026-07-01T00:00:00.000Z')
    expect(useApi().withGlobals()).toEqual({ cluster_id: 'c-1', as_of: '2026-07-01T00:00:00.000Z' })
    tt.backToNow()
    expect(useApi().withGlobals()).toEqual({ cluster_id: 'c-1' })
  })

  it('throws rather than emitting a query without cluster_id', () => {
    expect(() => useApi().withGlobals()).toThrow(/cluster_id/)
  })
})
