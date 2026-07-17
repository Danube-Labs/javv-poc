/**
 * The navigation gate as a pure function (M9f — FR-18/D33): session + capability checks
 * separated from the router so the decision table is unit-testable. The client gate is
 * CONVENIENCE ONLY — the server 403s the same capabilities (the RBAC/IDOR contract test
 * is the authority).
 */
import type { RouteLocationNormalized } from 'vue-router'

export interface GateSession {
  isAuthed: boolean
  mustChange: boolean
  hasCapability: (cap: string) => boolean
}

export type GateDecision = true | { name: string }

export function resolveGate(auth: GateSession, to: RouteLocationNormalized): GateDecision {
  if (to.name === 'login') {
    return auth.isAuthed && !auth.mustChange ? { name: 'overview' } : true
  }
  if (!auth.isAuthed || auth.mustChange) return { name: 'login' }

  const cap = to.meta.capability as string | undefined
  if (cap && !auth.hasCapability(cap)) return { name: 'overview' }
  return true
}
