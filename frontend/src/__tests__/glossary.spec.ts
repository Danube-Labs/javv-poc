/**
 * The Guide's glossary (issue 341): a term that is also a findings filter must show that
 * filter's live label, so renaming the filter can't leave the glossary describing a label
 * nobody sees. And the copy stays plain: no em dashes (operator ruling 2026-10-01).
 */
import { describe, expect, it } from 'vitest'

import { GLOSSARY, filterLabel, glossaryTerm } from '@/about/glossary'
import { FINDINGS_FIELDS, type FilterField } from '@/filters/fields.config'

describe('filterLabel', () => {
  const fields: FilterField[] = [
    { key: 'severity', label: 'Severity', type: 'terms', param: 'severity' },
    {
      key: 'attr',
      label: 'Attribute',
      type: 'flags',
      values: [{ key: 'kev', param: 'kev', label: 'KEV' }],
    },
  ] as FilterField[]

  it("returns a field's own label", () => {
    expect(filterLabel(fields, 'severity')).toBe('Severity')
  })
  it("returns a flags field's value label", () => {
    expect(filterLabel(fields, 'kev')).toBe('KEV')
  })
  it('returns null for a key no field knows', () => {
    expect(filterLabel(fields, 'nope')).toBeNull()
  })
})

describe('GLOSSARY', () => {
  it('every filter term resolves to a live findings filter label', () => {
    for (const entry of GLOSSARY) {
      if ('filter' in entry.term) {
        expect(filterLabel(FINDINGS_FIELDS, entry.term.filter), entry.term.filter).not.toBeNull()
      }
    }
  })

  it('shows the filter labels the findings screen shows', () => {
    const terms = GLOSSARY.map(glossaryTerm)
    expect(terms).toContain('Fix available')
    expect(terms).toContain('Scanners disagree')
    expect(terms).toContain('SLA breached')
    expect(terms).toContain('New in range')
  })

  it('has no duplicate terms', () => {
    const terms = GLOSSARY.map(glossaryTerm)
    expect(new Set(terms).size).toBe(terms.length)
  })

  it('has no em dashes in any term or definition', () => {
    for (const entry of GLOSSARY) {
      expect(`${glossaryTerm(entry)} ${entry.body}`).not.toContain('—')
    }
  })
})
