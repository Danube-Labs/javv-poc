/**
 * The health store says WHAT is down (issue 675): a 503 is the backend reporting its store; no
 * answer, or a proxy's 502 or 504, is the backend itself. The banner and the sidebar footer word
 * the two differently.
 */
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import BackendHealthBanner from '@/components/system/BackendHealthBanner.vue'
import { logger } from '@/lib/logger'
import { downReason, useHealthStore } from '@/stores/health'

const fetchMock = vi.fn<(url: string) => Promise<{ ok: boolean; status: number }>>()
const warned = vi.spyOn(logger, 'warn').mockImplementation(() => {})
vi.spyOn(logger, 'info').mockImplementation(() => {})

beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock.mockReset()
  warned.mockClear()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

describe('downReason', () => {
  it('a 503 is the backend reporting its store', () => expect(downReason(503)).toBe('store'))
  it.each([undefined, 500, 502, 504, 404])('%s is the backend itself', (status) => {
    expect(downReason(status)).toBe('backend')
  })
})

describe('the /readyz poll', () => {
  it('a 503 marks the store down', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 503 })
    const health = useHealthStore()
    await health.check()
    expect(health.degraded).toBe(true)
    expect(health.reason).toBe('store')
    expect(health.statusLabel).toBe('Store degraded')
    expect(warned).toHaveBeenCalledWith('backend degraded', { source: 'readyz', reason: 'store' })
  })

  it.each([
    ['a proxy error', () => Promise.resolve({ ok: false, status: 502 })],
    ['no answer', () => Promise.reject(new TypeError('Failed to fetch'))],
  ])('%s marks the backend down', async (_name, reply) => {
    fetchMock.mockImplementationOnce(reply)
    const health = useHealthStore()
    await health.check()
    expect(health.reason).toBe('backend')
    expect(health.statusLabel).toBe('Backend not answering')
  })

  it('a 200 clears the flag and the reason', async () => {
    const health = useHealthStore()
    health.markDegraded('backend', 'api')
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200 })
    await health.check()
    expect(health.degraded).toBe(false)
    expect(health.reason).toBeNull()
    expect(health.statusLabel).toBe('Store healthy')
  })

  it('logs once per reason, not once per poll', async () => {
    const health = useHealthStore()
    health.markDegraded('backend', 'api')
    health.markDegraded('backend', 'readyz')
    expect(warned).toHaveBeenCalledTimes(1)
    health.markDegraded('store', 'readyz')
    expect(warned).toHaveBeenCalledTimes(2)
  })

  it('a dismissed banner returns on the next signal', () => {
    const health = useHealthStore()
    health.markDegraded('store', 'api')
    health.dismiss()
    expect(health.bannerVisible).toBe(false)
    health.markDegraded('store', 'readyz')
    expect(health.bannerVisible).toBe(true)
  })
})

describe('BackendHealthBanner', () => {
  it('is absent while healthy', () => {
    expect(mount(BackendHealthBanner).find('[role="alert"]').exists()).toBe(false)
  })

  it('names the backend when the backend is gone', () => {
    useHealthStore().markDegraded('backend', 'api')
    const text = mount(BackendHealthBanner).get('[role="alert"]').text()
    expect(text).toContain('The backend is not answering')
    expect(text).not.toContain('OpenSearch')
  })

  it('names OpenSearch when the store is down', () => {
    useHealthStore().markDegraded('store', 'api')
    expect(mount(BackendHealthBanner).get('[role="alert"]').text()).toContain('Check OpenSearch health')
  })
})
