/**
 * The Audit log's way in (issue 681): its first page used to be all sign-ins, with triage and
 * settings changes pages down. The nav entry carries the filter in the address, so the page
 * shows a removable chip and a bare `/audit` still means every event.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { AUDIT_FIELDS } from '@/audit/fields.config'
import { NAV, visibleNav } from '@/components/chrome/navModel'
import { makeFiltersStore } from '@/stores/filters'

const auditEntry = () => NAV.flatMap((g) => g.items).find((i) => i.label === 'Audit log')!

beforeEach(() => setActivePinia(createPinia()))

describe('the Audit log nav entry', () => {
  it('opens the log with sign-ins filtered out, as an exclusion in the address', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/audit', component: { template: '<div />' } }],
    })
    await router.push(auditEntry().to)
    expect(router.currentRoute.value.path).toBe('/audit')

    const filters = makeFiltersStore('nav-model-audit', AUDIT_FIELDS)()
    filters.fromQuery(router.currentRoute.value.query)
    expect(filters.selections.action).toEqual(['login'])
    expect(filters.modes.action).toBe('not')
  })

  it('filters nothing else: every other audit field starts empty', async () => {
    const filters = makeFiltersStore('nav-model-audit-2', AUDIT_FIELDS)()
    filters.fromQuery({ action: '!login' })
    const others = AUDIT_FIELDS.filter((f) => f.key !== 'action').map((f) => filters.selections[f.key])
    expect(others.every((v) => (v ?? []).length === 0)).toBe(true)
  })

  it('is still listed for a user with no capabilities', () => {
    const labels = visibleNav(() => false).flatMap((g) => g.items.map((i) => i.label))
    expect(labels).toContain('Audit log')
  })
})
