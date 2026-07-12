/** D28 display clock: countdowns measure from T when rewound, from the wall clock at now. */

import { describe, expect, it } from 'vitest'

import { refNowMs } from '@/system/clock'

describe('refNowMs', () => {
  const wall = Date.parse('2026-07-12T12:00:00Z')

  it('returns the wall clock at now (t = null)', () => {
    expect(refNowMs(null, wall)).toBe(wall)
  })

  it('returns T when rewound — a deadline open at T must not read from today', () => {
    const t = '2026-07-08T23:59:59.999Z'
    expect(refNowMs(t, wall)).toBe(Date.parse(t))
  })

  it('falls back to the wall clock on an unparseable t', () => {
    expect(refNowMs('not-a-date', wall)).toBe(wall)
  })
})
