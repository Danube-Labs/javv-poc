/**
 * The bulk triage dialog when the current filters can't drive a bulk action (issue 674): it
 * says what to do and offers one way out, never a dead "Apply" beside a refusal.
 */
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import BulkTriageBar from '@/components/triage/BulkTriageBar.vue'
import { FINDINGS_FIELDS } from '@/filters/fields.config'

vi.mock('@/api/generated', () => ({ bulkTriageApiV1FindingsBulkTriagePost: vi.fn<() => Promise<unknown>>() }))

const open = async (selections: Record<string, string[]>) => {
  const w = mount(BulkTriageBar, {
    props: { fields: FINDINGS_FIELDS, selections, total: 12, canTriage: true, canAcceptFinal: true, historical: false },
    attachTo: document.body,
  })
  await w.findAll('button').find((b) => b.text().includes('Bulk triage'))!.trigger('click')
  return w
}
const buttons = () => [...document.body.querySelectorAll('button')].map((b) => b.textContent!.trim())

describe('BulkTriageBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
  })

  it('with no filter: says to add one, and offers Close alone', async () => {
    await open({})
    expect(document.body.textContent).toContain('Add a filter first.')
    expect(buttons()).toContain('Close')
    expect(buttons()).not.toContain('Cancel')
    expect(buttons().some((t) => t.startsWith('Apply'))).toBe(false)
  })

  it('with a filter it cannot follow: names the filter to remove, and offers Close alone', async () => {
    await open({ severity: ['critical'], namespace: ['payments'] })
    expect(document.body.textContent).toContain('Remove this filter first: Namespace.')
    expect(buttons().some((t) => t.startsWith('Apply'))).toBe(false)
  })

  it('with a usable filter: the form, with Cancel and Apply', async () => {
    await open({ severity: ['critical'] })
    expect(document.body.textContent).not.toContain('Add a filter first.')
    expect(buttons()).toContain('Cancel')
    expect(buttons().some((t) => t.startsWith('Apply'))).toBe(true)
  })
})
