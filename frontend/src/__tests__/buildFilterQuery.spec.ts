import { describe, expect, it } from 'vitest'

import { buildFilterQuery } from '@/filters/buildFilterQuery'
import { FINDINGS_FIELDS, emptySelections, type FilterField } from '@/filters/fields.config'

const CID = 'fcbcbe84-9da1-41fb-879e-83c3e0f995f0'
const sel = (over: Record<string, string[]> = {}) => ({ ...emptySelections(FINDINGS_FIELDS), ...over })

describe('buildFilterQuery', () => {
  it('always emits cluster_id, even with no selections', () => {
    expect(buildFilterQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID })).toEqual({ cluster_id: CID })
  })

  it('throws when cluster_id is missing (tenant chokepoint)', () => {
    expect(() => buildFilterQuery(FINDINGS_FIELDS, sel(), { cluster_id: '' })).toThrow(/cluster_id/)
  })

  it('omits as_of at T=now and passes it through when time-traveling (D28)', () => {
    expect(buildFilterQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID })).not.toHaveProperty('as_of')
    const t = '2026-07-01T00:00:00Z'
    expect(buildFilterQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID, as_of: t }).as_of).toBe(t)
  })

  it('emits multi-value terms as arrays, lowercased (D16 severity case-insensitive)', () => {
    const q = buildFilterQuery(FINDINGS_FIELDS, sel({ severity: ['CRITICAL', 'negligible'] }), {
      cluster_id: CID,
    })
    expect(q.severity).toEqual(['critical', 'negligible'])
  })

  it('emits single-value terms as scalars and refuses to merge two selections', () => {
    expect(
      buildFilterQuery(FINDINGS_FIELDS, sel({ scanner: ['trivy'] }), { cluster_id: CID }).scanner,
    ).toBe('trivy')
    expect(() =>
      buildFilterQuery(FINDINGS_FIELDS, sel({ scanner: ['trivy', 'grype'] }), { cluster_id: CID }),
    ).toThrow(/single value/)
  })

  it('maps selected flags to their own boolean params', () => {
    const q = buildFilterQuery(FINDINGS_FIELDS, sel({ attr: ['kev', 'disagree'] }), { cluster_id: CID })
    expect(q.kev).toBe(true)
    expect(q.disagree).toBe(true)
    expect(q).not.toHaveProperty('fixable')
  })

  it('trims text fields and drops blank ones', () => {
    const q = buildFilterQuery(FINDINGS_FIELDS, sel({ image: ['  nginx  '] }), {
      cluster_id: CID,
    })
    expect(q.image_repo).toBe('nginx')
    const blank = buildFilterQuery(FINDINGS_FIELDS, sel({ image: ['   '] }), { cluster_id: CID })
    expect(blank).not.toHaveProperty('image_repo')
  })

  it('rail dims namespace/assignee emit their single-value params', () => {
    const q = buildFilterQuery(FINDINGS_FIELDS, sel({ namespace: ['payments'], assignee: ['admin'] }), {
      cluster_id: CID,
    })
    expect(q.namespace).toBe('payments')
    expect(q.assignee).toBe('admin')
  })

  it('drives entirely off the config: a new field needs no builder change', () => {
    const fields: FilterField[] = [
      ...FINDINGS_FIELDS,
      { key: 'os', label: 'OS', type: 'terms', param: 'os_name', multi: true },
    ]
    const q = buildFilterQuery(fields, { ...sel(), os: ['Alpine'] }, { cluster_id: CID })
    expect(q.os_name).toEqual(['alpine'])
  })
})
