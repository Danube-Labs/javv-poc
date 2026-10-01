/**
 * The zero-clusters onboarding state (M9f): data screens show it while no scanner has enrolled,
 * because they would fetch nothing forever. Configure stays live (Settings → Tokens is the way
 * out) and so does Help (issue 341): the About page is what a new install needs most.
 */
import { describe, expect, it } from 'vitest'

import { isColdStart } from '@/system/coldStart'

const empty = { loaded: true, failed: false, clusterCount: 0 }

describe('isColdStart', () => {
  it('holds a data screen while the registry is loaded, healthy and empty', () => {
    expect(isColdStart({ ...empty, section: 'monitor' })).toBe(true)
    expect(isColdStart({ ...empty, section: undefined })).toBe(true)
  })

  it('never holds Configure or Help', () => {
    expect(isColdStart({ ...empty, section: 'configure' })).toBe(false)
    expect(isColdStart({ ...empty, section: 'help' })).toBe(false)
  })

  it('needs an answered, non-failed, empty registry', () => {
    expect(isColdStart({ ...empty, loaded: false, section: 'monitor' })).toBe(false)
    expect(isColdStart({ ...empty, failed: true, section: 'monitor' })).toBe(false)
    expect(isColdStart({ ...empty, clusterCount: 1, section: 'monitor' })).toBe(false)
  })
})
