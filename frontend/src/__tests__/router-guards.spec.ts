/**
 * The navigation gate decision table (M9f — FR-18/D33): every branch of resolveGate. The
 * client gate is convenience — the server-side 403 twin lives in the backend RBAC/IDOR
 * contract test (test_rbac_idor_contract.py); this spec pins the client half so a route
 * hidden from the nav can never be reached by URL either.
 */
import { describe, expect, it } from 'vitest'
import type { RouteLocationNormalized } from 'vue-router'

import { resolveGate, type GateSession } from '@/router/guards'

function session(over: Partial<GateSession> = {}): GateSession {
  return {
    isAuthed: true,
    mustChange: false,
    hasCapability: () => true,
    ...over,
  }
}

function to(name: string, capability?: string): RouteLocationNormalized {
  return { name, meta: capability ? { capability } : {} } as unknown as RouteLocationNormalized
}

describe('resolveGate — the navigation decision table', () => {
  it('unauthenticated → login, wherever they were headed', () => {
    expect(resolveGate(session({ isAuthed: false }), to('findings'))).toEqual({ name: 'login' })
    expect(resolveGate(session({ isAuthed: false }), to('settings-users'))).toEqual({
      name: 'login',
    })
  })

  it('must_change locks the whole app to login (SEC-6)', () => {
    expect(resolveGate(session({ mustChange: true }), to('overview'))).toEqual({ name: 'login' })
  })

  it('login route: authed users bounce to overview, others pass', () => {
    expect(resolveGate(session(), to('login'))).toEqual({ name: 'overview' })
    expect(resolveGate(session({ isAuthed: false }), to('login'))).toBe(true)
    expect(resolveGate(session({ mustChange: true }), to('login'))).toBe(true)
  })

  it('capability-gated route without the capability → overview (A-4)', () => {
    const auth = session({ hasCapability: (c) => c !== 'can_manage_users' })
    expect(resolveGate(auth, to('settings-users', 'can_manage_users'))).toEqual({
      name: 'overview',
    })
    expect(resolveGate(auth, to('settings-tokens', 'can_manage_tokens'))).toBe(true)
  })

  it('plain authed navigation passes', () => {
    expect(resolveGate(session(), to('findings'))).toBe(true)
  })
})
