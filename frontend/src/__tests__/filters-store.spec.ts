import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { makeFiltersStore } from '@/stores/filters'

const useStore = makeFiltersStore('test-filters', FINDINGS_FIELDS)

describe('filters store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('toggles multi-value terms on and off', () => {
    const s = useStore()
    s.toggle('severity', 'critical')
    s.toggle('severity', 'high')
    expect(s.selections.severity).toEqual(['critical', 'high'])
    s.toggle('severity', 'critical')
    expect(s.selections.severity).toEqual(['high'])
    expect(s.hasFilters).toBe(true)
  })

  it('replaces instead of accumulating on single-value terms', () => {
    const s = useStore()
    s.toggle('scanner', 'trivy')
    s.toggle('scanner', 'grype')
    expect(s.selections.scanner).toEqual(['grype'])
  })

  it('clearField and clearAll empty the selections', () => {
    const s = useStore()
    s.toggle('severity', 'low')
    s.setText('namespace', 'payments')
    s.clearField('severity')
    expect(s.selections.severity).toEqual([])
    expect(s.hasFilters).toBe(true)
    s.clearAll()
    expect(s.hasFilters).toBe(false)
  })

  it('round-trips selections through the URL query unchanged (bolt DoD)', () => {
    const s = useStore()
    s.toggle('severity', 'critical')
    s.toggle('severity', 'negligible')
    s.toggle('attr', 'kev')
    s.toggle('scanner', 'trivy')
    s.setText('namespace', 'payments')
    const snapshot = JSON.parse(JSON.stringify(s.selections))

    const query = s.toQuery()
    expect(query).toEqual({
      severity: 'critical,negligible',
      attr: 'kev',
      scanner: 'trivy',
      namespace: 'payments',
    })

    s.clearAll()
    s.fromQuery(query)
    expect(s.selections).toEqual(snapshot)
  })

  it('drops unknown vocabulary values and unknown keys from the URL', () => {
    const s = useStore()
    s.fromQuery({ severity: 'critical,BOGUS', attr: 'kev,nope', evil: 'x' })
    expect(s.selections.severity).toEqual(['critical'])
    expect(s.selections.attr).toEqual(['kev'])
    expect(s.selections).not.toHaveProperty('evil')
  })
})
