/**
 * Saved-view capture ⇄ apply (M9f slice 4) — the SCREENS §6 deep-link contract as a GOLDEN
 * round-trip: workbench state → stored preset → /findings route query → the exact API query
 * body. Drift anywhere in the chain breaks every stored view silently; the golden pins it.
 */
import { describe, expect, it } from 'vitest'

import { buildFilterQuery } from '@/filters/buildFilterQuery'
import { emptySelections, FINDINGS_FIELDS } from '@/filters/fields.config'
import {
  captureLens,
  facetsTotal,
  presetCountQuery,
  presetSummary,
  presetToRouteQuery,
} from '@/findings/savedViews'
import { makeFiltersStore } from '@/stores/filters'
import { createPinia, setActivePinia } from 'pinia'

const CID = 'fcbcbe84-9da1-41fb-879e-83c3e0f995f0'

/** THE golden workbench: negated severity + included namespace + two flags + search text. */
const SELECTIONS = {
  ...emptySelections(FINDINGS_FIELDS),
  severity: ['low', 'negligible'],
  namespace: ['payments'],
  attr: ['kev', 'new'],
  q: ['curl'],
}
const MODES = { severity: 'not' } as const

const GOLDEN_PRESET = {
  exclude_severity: ['low', 'negligible'],
  namespace: 'payments',
  kev: true,
  new_within_days: 7,
  q: 'curl',
}

const GOLDEN_ROUTE_QUERY = {
  q: 'curl',
  severity: '!low,!negligible',
  attr: 'kev,new',
  namespace: 'payments',
}

describe('saved views — the golden capture ⇄ apply round-trip (SCREENS §6)', () => {
  it('capture: workbench state → the stored preset (param-keyed, exclude family included)', () => {
    expect(captureLens(FINDINGS_FIELDS, SELECTIONS, MODES, 6.3)).toEqual(GOLDEN_PRESET)
  })

  it('apply: stored preset → the /findings route query (field-keyed, ! grammar)', () => {
    expect(presetToRouteQuery(FINDINGS_FIELDS, GOLDEN_PRESET as never)).toEqual(GOLDEN_ROUTE_QUERY)
  })

  it('round-trip: the applied URL re-emits the preset params EXACTLY (deep-link contract)', () => {
    setActivePinia(createPinia())
    const store = makeFiltersStore('golden-roundtrip', FINDINGS_FIELDS)()
    store.fromQuery(GOLDEN_ROUTE_QUERY)
    const body = buildFilterQuery(
      FINDINGS_FIELDS,
      store.selections,
      { cluster_id: CID, window_days: 6.3 },
      store.modes,
    )
    expect(body).toEqual({ cluster_id: CID, ...GOLDEN_PRESET })
  })

  it('card count query = preset params verbatim + tenant (facets — a size-0 agg, no PIT)', () => {
    expect(presetCountQuery(GOLDEN_PRESET as never, CID)).toEqual({
      cluster_id: CID,
      ...GOLDEN_PRESET,
    })
    expect(presetCountQuery({} as never, CID, '2026-07-01T00:00:00Z').as_of).toBe(
      '2026-07-01T00:00:00Z',
    )
  })

  it('facetsTotal sums the severity buckets — one severity per row makes it the lens total', () => {
    expect(facetsTotal({ facets: { severity: [{ count: 3 }, { count: 4 }] } })).toBe(7)
    expect(facetsTotal({ facets: { severity: [] } })).toBe(0)
    expect(facetsTotal({ facets: {} })).toBeNull()
    expect(facetsTotal({})).toBeNull()
    expect(facetsTotal(null)).toBeNull()
  })

  it('summary speaks the pill grammar, negation first-class', () => {
    const s = presetSummary(FINDINGS_FIELDS, GOLDEN_PRESET as never)
    expect(s).toContain('Severity is none of low, negligible')
    expect(s).toContain('Namespace is payments')
    expect(s).toContain('KEV')
    expect(presetSummary(FINDINGS_FIELDS, {} as never)).toBe('No filters — everything')
  })

  it('an empty workbench captures an empty preset — "everything" is a valid view', () => {
    expect(captureLens(FINDINGS_FIELDS, emptySelections(FINDINGS_FIELDS), {}, 30)).toEqual({})
  })
})
