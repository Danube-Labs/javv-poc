import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import LimitedHistoricalNotice from '@/components/dashboards/LimitedHistoricalNotice.vue'
import { useTimeTravelStore } from '@/stores/timeTravel'
import AllClustersView from '@/views/AllClustersView.vue'

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } })

vi.mock('@/api/generated', () => ({
  listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
  facetFindingsApiV1FindingsFacetsGet: vi.fn<() => Promise<unknown>>(),
  scannerFreshnessApiV1ScannersFreshnessGet: vi.fn<() => Promise<unknown>>(),
  listRunningImagesApiV1ImagesGet: vi.fn<() => Promise<unknown>>(),
}))
vi.mock('@/api/client', () => ({ client: {} }))

import {
  facetFindingsApiV1FindingsFacetsGet,
  listClustersApiV1ClustersGet,
  listRunningImagesApiV1ImagesGet,
  scannerFreshnessApiV1ScannersFreshnessGet,
} from '@/api/generated'

const listMock = vi.mocked(listClustersApiV1ClustersGet)
const facetsMock = vi.mocked(facetFindingsApiV1FindingsFacetsGet)
const freshMock = vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet)
const imagesMock = vi.mocked(listRunningImagesApiV1ImagesGet)

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div />' } },
    { path: '/overview', component: { template: '<div />' } },
  ],
})

const mountView = () => mount(AllClustersView, { global: { plugins: [router] } })

describe('AllClustersView (M9c slice 2)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('T<now replaces the screen with LimitedHistoricalNotice — no table, no query (I3)', async () => {
    useTimeTravelStore().t = '2026-07-01T00:00:00Z'
    const w = mountView()
    await flushPromises()
    expect(w.findComponent(LimitedHistoricalNotice).exists()).toBe(true)
    expect(w.find('table').exists()).toBe(false)
    expect(listMock).not.toHaveBeenCalled()
    expect(facetsMock).not.toHaveBeenCalled()
  })

  it('T=now renders a row per cluster with one mix bar PER SCANNER, never merged', async () => {
    listMock.mockResolvedValue(ok({ clusters: [{ cluster_id: 'c-1', cluster_name: 'prod' }] }) as never)
    facetsMock.mockResolvedValue(
      ok({
        facets: {
          severity: [
            { key: 'critical', count: 3, by_scanner: { trivy: 1, grype: 2 } },
            { key: 'low', count: 5, by_scanner: { trivy: 5 } },
          ],
          present: [{ key: 'true', count: 8, by_scanner: { trivy: 6, grype: 2 } }],
        },
      }) as never,
    )
    freshMock.mockResolvedValue(
      ok({ scanners: [{ scanner: 'trivy', last_ingest_at: '2026-07-10T12:00:00Z', silent_for_seconds: 60 }] }) as never,
    )
    imagesMock.mockResolvedValue(ok({ inventory: { inventory_run_id: 'r1' }, images: [{ replicas: 4 }] }) as never)

    const w = mountView()
    await flushPromises()

    expect(w.findComponent(LimitedHistoricalNotice).exists()).toBe(false)
    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.text()).toContain('prod')
    expect(rows[0]!.findAll('.mix-row')).toHaveLength(2) // trivy + grype, side by side
    expect(rows[0]!.text()).toContain('8') // present count verbatim
    // fleet strip: the critical cell shows the server bucket count
    expect(w.find('.fleet-band').text()).toContain('critical')
    // signal columns (operator A/B ruling: explicit columns) — headers + per-row values
    const headers = w.findAll('th').map((h) => h.text())
    for (const h of ['KEV', 'Fix %', 'Disagree', 'Triage']) expect(headers).toContain(h)
    expect(rows[0]!.find('.kev-alarm').exists()).toBe(false) // kev bucket absent → 0, no alarm
    expect(rows[0]!.text()).toContain('%') // fix % renders
  })

  it('no clusters → the cold-start copy, not an empty table', async () => {
    listMock.mockResolvedValue(ok({ clusters: [] }) as never)
    const w = mountView()
    await flushPromises()
    expect(w.find('.first-run').exists()).toBe(true)
    expect(w.find('table').exists()).toBe(false)
  })
})
