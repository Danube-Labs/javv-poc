import { afterEach, describe, expect, it, vi } from 'vitest'

import { logger } from '@/lib/logger'

afterEach(() => vi.restoreAllMocks())

describe('logger', () => {
  it('emits the backend-shaped structured line: timestamp → level → event → fields', () => {
    const spy = vi.spyOn(console, 'info').mockImplementation(() => {})
    logger.info('view mounted', { view: 'findings', cluster_id: 'c-1' })
    expect(spy).toHaveBeenCalledOnce()
    const line = spy.mock.calls[0]![0] as Record<string, unknown>
    expect(Object.keys(line).slice(0, 3)).toEqual(['timestamp', 'level', 'event'])
    expect(line).toMatchObject({ level: 'info', event: 'view mounted', view: 'findings', cluster_id: 'c-1' })
    expect(typeof line.timestamp).toBe('string')
  })

  it('routes each level to its console method', () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    logger.error('request failed', { status: 503 })
    logger.warn('retrying', { attempt: 2 })
    expect(err).toHaveBeenCalledOnce()
    expect(warn).toHaveBeenCalledOnce()
  })

  it('suppresses events below the configured threshold', () => {
    vi.stubEnv('VITE_LOG_LEVEL', 'warn')
    const info = vi.spyOn(console, 'info').mockImplementation(() => {})
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    logger.info('too quiet')
    logger.warn('loud enough')
    expect(info).not.toHaveBeenCalled()
    expect(warn).toHaveBeenCalledOnce()
    vi.unstubAllEnvs()
  })
})
