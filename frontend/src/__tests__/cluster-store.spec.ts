/**
 * Cluster selection precedence (issue 433): a deep link's ?cluster= beats the remembered
 * selection beats the first registry entry; an unknown link id falls back LOUDLY (toast) and
 * is never persisted — a colleague's link must not flip this browser's default.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } })

vi.mock('@/api/generated', () => ({
  listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
}))
vi.mock('@/api/client', () => ({ client: {} }))

import { listClustersApiV1ClustersGet } from '@/api/generated'

const listMock = vi.mocked(listClustersApiV1ClustersGet)

const REGISTRY = ok({
  clusters: [
    { cluster_id: 'c-alpha-11', cluster_name: 'alpha' },
    { cluster_id: 'c-beta-22', cluster_name: 'beta' },
  ],
})

describe('cluster store — deep-link selection precedence (issue 433)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('a valid ?cluster= beats the remembered selection', async () => {
    localStorage.setItem('javv.selected_cluster_id', 'c-alpha-11')
    listMock.mockResolvedValue(REGISTRY as never)
    const s = useClusterStore()
    await s.fetchClusters('c-beta-22')
    expect(s.selectedId).toBe('c-beta-22')
    // the link's choice is NOT persisted — the browser default stays alpha
    expect(localStorage.getItem('javv.selected_cluster_id')).toBe('c-alpha-11')
  })

  it('an unknown link id falls back to the remembered selection and toasts', async () => {
    localStorage.setItem('javv.selected_cluster_id', 'c-beta-22')
    listMock.mockResolvedValue(REGISTRY as never)
    const s = useClusterStore()
    await s.fetchClusters('c-gone-99')
    expect(s.selectedId).toBe('c-beta-22')
    expect(useToastStore().toasts.length).toBeGreaterThan(0)
  })

  it('no link, no memory → first registry entry (the pre-433 behavior)', async () => {
    listMock.mockResolvedValue(REGISTRY as never)
    const s = useClusterStore()
    await s.fetchClusters()
    expect(s.selectedId).toBe('c-alpha-11')
  })
})
