import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAllClustersStore } from '@/stores/allClusters'

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } })

vi.mock('@/api/generated', () => ({
  listClustersApiV1ClustersGet: vi.fn(),
  facetFindingsApiV1FindingsFacetsGet: vi.fn(),
  scannerFreshnessApiV1ScannersFreshnessGet: vi.fn(),
  listRunningImagesApiV1ImagesGet: vi.fn(),
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

describe('all-clusters store (M9c slice 2)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('I3 guard: T<now flips limited and emits NO query — not even the cluster list', async () => {
    const s = useAllClustersStore()
    await s.load('2026-07-01T00:00:00Z')
    expect(s.limited).toBe(true)
    expect(s.rows).toEqual([])
    expect(listMock).not.toHaveBeenCalled()
    expect(facetsMock).not.toHaveBeenCalled()
    expect(freshMock).not.toHaveBeenCalled()
    expect(imagesMock).not.toHaveBeenCalled()
  })

  it('T=now loads one row set per cluster, each call carrying that cluster_id', async () => {
    listMock.mockResolvedValue(
      ok({
        clusters: [
          { cluster_id: 'c-1', cluster_name: 'prod' },
          { cluster_id: 'c-2', cluster_name: 'c-2' },
        ],
      }) as never,
    )
    facetsMock.mockResolvedValue(
      ok({ facets: { severity: [{ key: 'critical', count: 3, by_scanner: { trivy: 1, grype: 2 } }] } }) as never,
    )
    freshMock.mockResolvedValue(
      ok({ scanners: [{ scanner: 'trivy', last_ingest_at: '2026-07-10T12:00:00Z', silent_for_seconds: 60 }] }) as never,
    )
    imagesMock.mockResolvedValue(
      ok({ inventory: { inventory_run_id: 'r1' }, images: [{ replicas: 2 }, { replicas: 3 }] }) as never,
    )

    const s = useAllClustersStore()
    await s.load(null)

    expect(s.limited).toBe(false)
    expect(s.rows).toHaveLength(2)
    for (const call of [...facetsMock.mock.calls, ...freshMock.mock.calls, ...imagesMock.mock.calls]) {
      expect(['c-1', 'c-2']).toContain((call[0] as { query: { cluster_id: string } }).query.cluster_id)
    }
    // server buckets stored verbatim — by_scanner split intact, never merged
    expect(s.rows[0]!.facets.severity![0]!.by_scanner).toEqual({ trivy: 1, grype: 2 })
    expect(s.rows[0]!.imagesCount).toBe(2)
    expect(s.rows[0]!.replicas).toBe(5)
  })

  it('no committed inventory (inventory: null) stays unknown — null, not zero', async () => {
    listMock.mockResolvedValue(ok({ clusters: [{ cluster_id: 'c-1', cluster_name: 'c-1' }] }) as never)
    facetsMock.mockResolvedValue(ok({ facets: {} }) as never)
    freshMock.mockResolvedValue(ok({ scanners: [] }) as never)
    imagesMock.mockResolvedValue(ok({ inventory: null, images: [] }) as never)

    const s = useAllClustersStore()
    await s.load(null)
    expect(s.rows[0]!.imagesCount).toBeNull()
    expect(s.rows[0]!.replicas).toBeNull()
  })

  it('one failed cluster degrades its own row, not the fleet', async () => {
    listMock.mockResolvedValue(
      ok({
        clusters: [
          { cluster_id: 'c-1', cluster_name: 'c-1' },
          { cluster_id: 'c-2', cluster_name: 'c-2' },
        ],
      }) as never,
    )
    facetsMock
      .mockResolvedValueOnce({ data: null, response: { ok: false, status: 500 } } as never)
      .mockResolvedValueOnce(ok({ facets: {} }) as never)
    freshMock.mockResolvedValue(ok({ scanners: [] }) as never)
    imagesMock.mockResolvedValue(ok({ inventory: null, images: [] }) as never)

    const s = useAllClustersStore()
    await s.load(null)
    expect(s.failed).toBe(false)
    expect(s.rows.map((r) => r.failed)).toEqual([true, false])
  })

  it('a failed cluster LIST fails the screen', async () => {
    listMock.mockResolvedValue({ data: null, response: { ok: false, status: 503 } } as never)
    const s = useAllClustersStore()
    await s.load(null)
    expect(s.failed).toBe(true)
    expect(s.rows).toEqual([])
  })
})
