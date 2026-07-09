/**
 * The FR-7 VEX coupling, client-side: justification required iff not_affected, never sent with
 * any other state, stale unreachable by hand, empty drafts produce nothing to save.
 */
import { describe, expect, it } from 'vitest'

import { buildTriagePatch, CISA_JUSTIFICATIONS, PANEL_TARGETS } from '@/findings/triageRules'

const base = { currentState: 'open', targetState: null, vexJustification: null, notes: '', assignee: null }

describe('triage rules (FR-7 two-field VEX)', () => {
  it('not_affected requires a CISA justification — blocked without one', () => {
    const blocked = buildTriagePatch({ ...base, targetState: 'not_affected' })
    expect(blocked.body).toBeNull()
    expect(blocked.error).toMatch(/justification/)

    const ok = buildTriagePatch({
      ...base,
      targetState: 'not_affected',
      vexJustification: 'component_not_present',
    })
    expect(ok.error).toBeNull()
    expect(ok.body).toEqual({ state: 'not_affected', vex_justification: 'component_not_present' })
  })

  it('a justification never rides along with any other state', () => {
    const r = buildTriagePatch({ ...base, targetState: 'acknowledged', vexJustification: 'component_not_present' })
    expect(r.body).toEqual({ state: 'acknowledged' }) // dropped, not sent for the server to 422
  })

  it('stale is system-only; an unchanged state sends nothing', () => {
    expect(buildTriagePatch({ ...base, targetState: 'stale' }).error).toMatch(/system-set/)
    const noop = buildTriagePatch({ ...base, targetState: 'open' })
    expect(noop.body).toBeNull()
    expect(noop.error).toBeNull()
  })

  it('notes/assignee patch alone is valid; whitespace notes are not a patch', () => {
    expect(buildTriagePatch({ ...base, notes: ' context ' }).body).toEqual({ notes: 'context' })
    expect(buildTriagePatch({ ...base, assignee: 'admin' }).body).toEqual({ assignee: 'admin' })
    expect(buildTriagePatch({ ...base, notes: '   ' }).body).toBeNull()
  })

  it('panel targets exclude stale and risk_accepted; the CISA five are exactly five', () => {
    const targets = PANEL_TARGETS.map((t) => t.state)
    expect(targets).not.toContain('stale')
    expect(targets).not.toContain('risk_accepted')
    expect(CISA_JUSTIFICATIONS).toHaveLength(5)
    expect(CISA_JUSTIFICATIONS.filter((j) => j.maps === 'False positive')).toHaveLength(2)
  })
})
