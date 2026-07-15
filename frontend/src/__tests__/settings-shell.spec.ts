/**
 * M9e slice 1 — the pure settings logic: the SLA form contract guards (parse/build/dirt) and
 * the §13 section registry's invariants. Panel rendering is the browser smoke's job.
 */
import { describe, expect, it } from 'vitest'

import type { SlaPolicy } from '@/api/generated'
import { SETTINGS_SECTIONS } from '@/views/settings/sections'
import {
  draftFromPolicy,
  isDirty,
  parseWindow,
  policyFromDraft,
  SLA_KEYS,
} from '@/views/settings/slaForm'

const POLICY: SlaPolicy = {
  critical_days: 2,
  high_days: 7,
  medium_days: 30,
  low_days: 90,
  kev_days: 1,
}

describe('slaForm', () => {
  it('round-trips a policy through the draft', () => {
    expect(policyFromDraft(draftFromPolicy(POLICY))).toEqual(POLICY)
  })

  it('parseWindow: positive finite numbers only (the backend gt=0 guard)', () => {
    expect(parseWindow('7')).toBe(7)
    expect(parseWindow(' 0.5 ')).toBe(0.5) // fractional days are legal (12h KEV window)
    for (const bad of ['', '0', '-3', 'abc', '1e999', 'Infinity', 'NaN', '7d']) {
      expect.soft(parseWindow(bad), bad).toBeNull()
    }
  })

  it('policyFromDraft is all-or-nothing — one invalid window kills the PUT body', () => {
    const draft = draftFromPolicy(POLICY)
    draft.medium_days = '0'
    expect(policyFromDraft(draft)).toBeNull()
  })

  it('dirt is semantic: reformatting is clean, value changes and invalid edits are dirty', () => {
    const draft = draftFromPolicy(POLICY)
    expect(isDirty(draft, POLICY)).toBe(false)
    draft.high_days = '7.0' // same value, different spelling
    expect(isDirty(draft, POLICY)).toBe(false)
    draft.high_days = '14'
    expect(isDirty(draft, POLICY)).toBe(true)
    draft.high_days = 'x' // invalid edit must read dirty (and invalid), never silently clean
    expect(isDirty(draft, POLICY)).toBe(true)
  })

  it('draft covers exactly the SlaPolicy knobs', () => {
    expect(Object.keys(draftFromPolicy(POLICY)).sort()).toEqual([...SLA_KEYS].sort())
  })
})

describe('settings section registry (§13)', () => {
  it('keys are unique route segments', () => {
    const keys = SETTINGS_SECTIONS.map((s) => s.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('every section carries a real capability gate (A-4 bundles use these names)', () => {
    const known = new Set([
      'can_manage_settings',
      'can_manage_tokens',
      'can_manage_users',
      'can_manage_retention',
    ])
    for (const s of SETTINGS_SECTIONS) expect.soft(known.has(s.capability), s.key).toBe(true)
  })
})
