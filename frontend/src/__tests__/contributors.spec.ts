/** M9d slice 3 — the Contributors pure view-model: ordering, identity derivations, formats.
 * Every number stays the server's; these pins guard the presentation math only. */

import { describe, expect, it } from 'vitest'

import {
  actorTone,
  ackOf,
  daysFromWindow,
  fmtMedian,
  initials,
  resolvedOf,
  slaTier,
  sortBoard,
  type BoardRow,
} from '@/contributors/viewModel'
import { CHART_PTYPE_RAMP } from '@/styles/tokens'

const row = (actor: string, by: Record<string, number>, handled = 0, actions = 0): BoardRow => ({
  actor,
  actions: actions || Object.values(by).reduce((a, b) => a + b, 0),
  by_action: by,
  handled,
  median_ttr_seconds: null,
  sla_hit_pct: null,
})

describe('sortBoard', () => {
  it('ranks by resolved, then handled, then actions, then name — deterministic', () => {
    const rows = [
      row('bo', { resolve: 1 }, 1),
      row('ana', { resolve: 3 }, 3),
      row('cy', { resolve: 1, acknowledge: 2 }, 3),
      row('dee', { note: 9 }, 0),
    ]
    expect(sortBoard(rows).map((r) => r.actor)).toEqual(['ana', 'cy', 'bo', 'dee'])
    // equal on every metric → name decides, so the podium can't flicker
    const tied = [row('zoe', { resolve: 2 }, 2), row('abe', { resolve: 2 }, 2)]
    expect(sortBoard(tied).map((r) => r.actor)).toEqual(['abe', 'zoe'])
  })

  it('never mutates the wire order', () => {
    const rows = [row('b', { resolve: 1 }), row('a', { resolve: 2 })]
    sortBoard(rows)
    expect(rows.map((r) => r.actor)).toEqual(['b', 'a'])
  })
})

describe('by_action extractors', () => {
  it('read resolve/acknowledge, defaulting 0', () => {
    const r = row('x', { resolve: 4 })
    expect(resolvedOf(r)).toBe(4)
    expect(ackOf(r)).toBe(0)
  })
})

describe('initials', () => {
  it('takes the first two word-ish parts, else the first two chars', () => {
    expect(initials('dragos.daniel')).toBe('DD')
    expect(initials('ana-maria_p')).toBe('AM')
    expect(initials('admin')).toBe('AD')
    expect(initials('x')).toBe('X')
  })
})

describe('actorTone', () => {
  it('is deterministic and stays on the sanctioned categorical ramp', () => {
    expect(actorTone('admin')).toBe(actorTone('admin'))
    expect(CHART_PTYPE_RAMP).toContain(actorTone('admin'))
    expect(CHART_PTYPE_RAMP).toContain(actorTone('dragos.daniel'))
  })
})

describe('fmtMedian', () => {
  it('formats days, hours, sub-hour, and the no-sample dash', () => {
    expect(fmtMedian(null)).toBe('—')
    expect(fmtMedian(3 * 86_400)).toBe('3d')
    expect(fmtMedian(1.5 * 86_400)).toBe('1.5d')
    expect(fmtMedian(18 * 3_600)).toBe('18h')
    expect(fmtMedian(600)).toBe('<1h')
  })
})

describe('slaTier', () => {
  it('pins the prototype thresholds: ≥88 good · ≥80 ok · else low · null none', () => {
    expect(slaTier(null)).toBeNull()
    expect(slaTier(100)).toBe('good')
    expect(slaTier(88)).toBe('good')
    expect(slaTier(87.9)).toBe('ok')
    expect(slaTier(80)).toBe('ok')
    expect(slaTier(79.9)).toBe('low')
  })
})

describe('daysFromWindow', () => {
  it('maps the trend window to the endpoint int, clamped 1..365', () => {
    expect(daysFromWindow(30)).toBe(30)
    expect(daysFromWindow(1)).toBe(1)
    expect(daysFromWindow(0.5)).toBe(1) // Last 12h → 1 day
    expect(daysFromWindow(400)).toBe(365)
  })
})
