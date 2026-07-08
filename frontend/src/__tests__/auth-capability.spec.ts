import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useAuthStore, type SessionUser } from '@/stores/auth'

beforeEach(() => setActivePinia(createPinia()))

function withUser(capabilities: string[], must_change = false): ReturnType<typeof useAuthStore> {
  const auth = useAuthStore()
  auth.user = { username: 'u', role: 'x', capabilities, must_change } satisfies SessionUser
  return auth
}

describe('capability gating (D33/A-4 — capabilities, never role names)', () => {
  it('"*" grants everything (admin bundle)', () => {
    const auth = withUser(['*'])
    expect(auth.hasCapability('can_manage_settings')).toBe(true)
    expect(auth.hasCapability('can_accept_audit_final')).toBe(true)
  })

  it('exact capability match only — no prefix/role magic', () => {
    const auth = withUser(['can_triage'])
    expect(auth.hasCapability('can_triage')).toBe(true)
    expect(auth.hasCapability('can_manage_settings')).toBe(false)
    expect(auth.hasCapability('can')).toBe(false)
  })

  it('no session → no capability', () => {
    const auth = useAuthStore()
    expect(auth.hasCapability('can_triage')).toBe(false)
  })

  it('must_change is surfaced for the router lock', () => {
    expect(withUser(['*'], true).mustChange).toBe(true)
  })
})
