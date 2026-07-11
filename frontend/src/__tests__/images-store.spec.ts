import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useImagesStore } from '@/stores/images'

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } })

vi.mock('@/api/generated', () => ({
  listRunningImagesApiV1ImagesGet: vi.fn<() => Promise<unknown>>(),
}))
vi.mock('@/api/client', () => ({ client: {} }))

import { listRunningImagesApiV1ImagesGet } from '@/api/generated'

const listMock = vi.mocked(listRunningImagesApiV1ImagesGet)

const row = (digest: string) => ({
  image_digest: digest,
  image_repo: 'docker.io/library/nginx',
  tag: '1.21.6',
  namespaces: ['javv-smoke'],
  scanners: ['trivy'],
  crit: 28,
  high: 181,
  med: 302,
  low: 226,
  negligible: 0,
  unknown: 24,
  total: 761,
  fixable: 430,
  replicas: 3,
  trivy_count: 761,
  grype_count: 746,
  count_delta: 15,
  '@timestamp': '2026-07-08T21:06:56.140189+00:00',
})

describe('images store (M9c slice 3)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('stores manifest + rows verbatim, and the emitted query carries cluster_id + as_of', async () => {
    listMock.mockResolvedValue(
      ok({
        inventory: { inventory_run_id: 'r1', inventory_order: 4, started_at: null, completed_at: null },
        images: [row('sha256:aa')],
      }) as never,
    )
    const s = useImagesStore()
    await s.load({ cluster_id: 'c-1', as_of: '2026-07-01T00:00:00Z' })
    expect(listMock.mock.calls[0]![0]).toMatchObject({
      query: { cluster_id: 'c-1', as_of: '2026-07-01T00:00:00Z' },
    })
    expect(s.inventory?.inventory_run_id).toBe('r1')
    expect(s.images[0]!.count_delta).toBe(15) // D5b pair passes through untouched
    expect(s.unknown).toBe(false)
  })

  it('inventory null = unknown (no committed run at T), distinct from a committed empty run', async () => {
    listMock.mockResolvedValue(ok({ inventory: null, images: [] }) as never)
    const s = useImagesStore()
    await s.load({ cluster_id: 'c-1' })
    expect(s.unknown).toBe(true)

    listMock.mockResolvedValue(
      ok({ inventory: { inventory_run_id: 'r2', inventory_order: 5, started_at: null, completed_at: null }, images: [] }) as never,
    )
    await s.load({ cluster_id: 'c-1' })
    expect(s.unknown).toBe(false) // committed and EMPTY is a real answer
    expect(s.images).toEqual([])
  })

  it('a failed read flags failed and never fakes an empty inventory', async () => {
    listMock.mockResolvedValue({ data: null, response: { ok: false, status: 503 } } as never)
    const s = useImagesStore()
    await s.load({ cluster_id: 'c-1' })
    expect(s.failed).toBe(true)
    expect(s.unknown).toBe(false)
  })
})
