/**
 * The shared SDK mock (issue 707): a spec's `vi.mock('@/api/generated', ...)` factory built from
 * the real module, so no spec can leave out a call the code it mounts imports.
 */
import { describe, expect, it, vi } from 'vitest'

import { mockSdk } from './helpers/mockSdk'

const real = () => import('@/api/generated') as Promise<Record<string, unknown>>

describe('mockSdk', () => {
  it('stubs every function the real SDK exports', async () => {
    const actual = await real()
    const mocked = await mockSdk(real)
    const functions = Object.keys(actual).filter((k) => typeof actual[k] === 'function')
    expect(functions.length).toBeGreaterThan(0)
    for (const name of functions) expect(vi.isMockFunction(mocked[name])).toBe(true)
  })

  it('lets the spec override any call', async () => {
    const own = vi.fn<() => Promise<unknown>>().mockResolvedValue({ data: 'mine' })
    const mocked = await mockSdk(real, { getMetaApiV1MetaGet: own })
    expect(mocked.getMetaApiV1MetaGet).toBe(own)
  })

  it('rejects an unmocked call with its name, so the failure points at the gap', async () => {
    const mocked = await mockSdk(real)
    const call = mocked.listClustersApiV1ClustersGet as () => Promise<unknown>
    await expect(call()).rejects.toThrow('listClustersApiV1ClustersGet is not mocked in this spec')
  })
})
