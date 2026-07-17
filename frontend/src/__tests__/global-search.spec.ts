/**
 * Global search composable (M9f slice 2 / SCREENS.md §15): the emitted query params are the
 * contract — composed findings-GROUPS queries (cve_id / image_repo / namespaces), never a
 * bespoke endpoint; server counts pass through untouched; stale answers can never overwrite
 * newer ones. Plus the nav model's capability gating (shared by SideNav + palette).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { visibleNav } from '@/components/chrome/navModel'
import { useGlobalSearch, GROUP_SIZE, SEARCH_DIMS } from '@/composables/useGlobalSearch'

const groupsMock = vi.hoisted(() => vi.fn<(opts: { query: Record<string, unknown> }) => unknown>())
vi.mock('@/api/generated', () => ({ groupFindingsApiV1FindingsGroupsGet: groupsMock }))
vi.mock('@/api/client', () => ({ client: {} }))

function ok(buckets: Array<{ key: string; count: number }>) {
  return {
    response: { ok: true },
    data: { data: buckets.map((b) => ({ ...b, by_scanner: {} })), next_cursor: null },
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  groupsMock.mockReset()
})
afterEach(() => vi.useRealTimers())

describe('useGlobalSearch — emitted params (the §15 contract)', () => {
  it('one groups call per dim, same q/cluster/size, cluster_id always present', async () => {
    groupsMock.mockResolvedValue(ok([{ key: 'CVE-2026-1', count: 3 }]) as never)
    const gs = useGlobalSearch(() => 'c-1')
    gs.search('cve-2026')
    await vi.runAllTimersAsync()

    expect(groupsMock).toHaveBeenCalledTimes(SEARCH_DIMS.length)
    const bys = groupsMock.mock.calls.map(([opts]) => opts.query.by)
    expect(bys).toEqual(['cve_id', 'image_repo', 'namespaces'])
    for (const [opts] of groupsMock.mock.calls) {
      expect(opts.query).toMatchObject({ cluster_id: 'c-1', q: 'cve-2026', size: GROUP_SIZE })
    }
    expect(gs.results.value.cves).toEqual([{ key: 'CVE-2026-1', count: 3 }])
  })

  it('debounces: three fast keystrokes → one round of calls', async () => {
    groupsMock.mockResolvedValue(ok([]) as never)
    const gs = useGlobalSearch(() => 'c-1')
    gs.search('me')
    gs.search('mem')
    gs.search('memc')
    await vi.runAllTimersAsync()
    expect(groupsMock).toHaveBeenCalledTimes(SEARCH_DIMS.length)
    expect(groupsMock.mock.calls[0]?.[0].query.q).toBe('memc')
  })

  it('under the minimum length: no call, results cleared', async () => {
    const gs = useGlobalSearch(() => 'c-1')
    gs.search('a')
    await vi.runAllTimersAsync()
    expect(groupsMock).not.toHaveBeenCalled()
    expect(gs.results.value).toEqual({ cves: [], images: [], namespaces: [] })
  })

  it('no cluster selected: no call fires', async () => {
    const gs = useGlobalSearch(() => null)
    gs.search('memcached')
    await vi.runAllTimersAsync()
    expect(groupsMock).not.toHaveBeenCalled()
  })

  it('a stale answer never overwrites a newer one', async () => {
    let releaseFirst!: (v: unknown) => void
    const first = new Promise((r) => (releaseFirst = r))
    groupsMock
      .mockReturnValueOnce(first as never) // slow round, all three share the gate
      .mockReturnValueOnce(first as never)
      .mockReturnValueOnce(first as never)
      .mockResolvedValue(ok([{ key: 'ns-new', count: 1 }]) as never)

    const gs = useGlobalSearch(() => 'c-1')
    gs.search('old')
    await vi.advanceTimersByTimeAsync(300) // first round is now in flight, unresolved
    gs.search('new')
    await vi.advanceTimersByTimeAsync(300) // second round resolves
    releaseFirst(ok([{ key: 'ns-OLD', count: 9 }]))
    await vi.runAllTimersAsync()
    expect(gs.results.value.namespaces).toEqual([{ key: 'ns-new', count: 1 }])
  })

  it('a failed leg flags degraded and clears results (honest error, no partials)', async () => {
    groupsMock
      .mockResolvedValueOnce(ok([{ key: 'x', count: 1 }]) as never)
      .mockResolvedValueOnce({ response: { ok: false, status: 503 }, data: null } as never)
      .mockResolvedValueOnce(ok([]) as never)
    const gs = useGlobalSearch(() => 'c-1')
    gs.search('anything')
    await vi.runAllTimersAsync()
    expect(gs.failed.value).toBe(true)
    expect(gs.results.value).toEqual({ cves: [], images: [], namespaces: [] })
  })
})

describe('navModel — capability gating shared by SideNav + palette', () => {
  it('gated items vanish without the capability; empty groups drop', () => {
    const none = visibleNav(() => false)
    const flat = none.flatMap((g) => g.items.map((i) => i.label))
    expect(flat).not.toContain('Approval list')
    expect(flat).not.toContain('Settings')
    expect(none.some((g) => g.group === 'Configure')).toBe(false)
  })

  it('everything shows for the admin bundle', () => {
    const all = visibleNav(() => true)
    const flat = all.flatMap((g) => g.items.map((i) => i.label))
    expect(flat).toContain('Approval list')
    expect(flat).toContain('Settings')
    expect(flat).toContain('Findings')
  })
})
