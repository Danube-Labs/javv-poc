/**
 * The scanner freshness banner (FR-6/D20, issue 341): it appears only when a scanner has been
 * silent past the cluster's freshness window, and then carries a "What this means" link to
 * the Guide's freshness section. The copy stays plain: no em dash (operator ruling 2026-10-01).
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { scannerFreshnessApiV1ScannersFreshnessGet } from '@/api/generated'
import ScannerFreshnessBanner from '@/components/system/ScannerFreshnessBanner.vue'
import { useClusterStore } from '@/stores/cluster'

vi.mock('@/api/generated', () => ({
  scannerFreshnessApiV1ScannersFreshnessGet: vi.fn<() => Promise<unknown>>(),
  getStalenessApiV1SettingsStalenessGet: vi.fn<() => Promise<unknown>>().mockResolvedValue({
    data: { staleness: { freshness_days: 3, scanner_down_days: 7 }, per_cluster_override: false },
    response: { ok: true, status: 200 },
  }),
}))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
})

const DAY = 86_400
const freshness = (silentDays: number) => ({
  data: {
    scanners: [
      { scanner: 'trivy', last_ingest_at: '2026-09-27T08:34:00Z', silent_for_seconds: silentDays * DAY },
      { scanner: 'grype', last_ingest_at: '2026-10-01T08:30:00Z', silent_for_seconds: 60 },
    ],
  },
  response: { ok: true, status: 200 },
})

async function mountBanner() {
  const w = mount(ScannerFreshnessBanner, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

beforeEach(() => {
  setActivePinia(createPinia())
  const clusters = useClusterStore()
  clusters.selectedId = 'c-1'
})
afterEach(() => vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockReset())

describe('ScannerFreshnessBanner', () => {
  it('stays hidden while every scanner is inside the freshness window', async () => {
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(freshness(2) as never)
    const w = await mountBanner()
    expect(w.find('[role=alert]').exists()).toBe(false)
    w.unmount()
  })

  it('names the silent scanner and links to the guide section on freshness', async () => {
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(freshness(4) as never)
    const w = await mountBanner()
    const banner = w.find('[role=alert]')
    expect(banner.text()).toContain('trivy silent 4 days')
    expect(banner.text()).not.toContain('grype')
    const link = banner.find('a.gl-text')
    expect(link.text()).toBe('What this means')
    expect(link.attributes('href')).toBe('/guide#scans-and-freshness')
    w.unmount()
  })

  it('has no em dash in its copy', async () => {
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(freshness(4) as never)
    const w = await mountBanner()
    expect(w.find('[role=alert]').text()).not.toContain('—')
    w.unmount()
  })
})
