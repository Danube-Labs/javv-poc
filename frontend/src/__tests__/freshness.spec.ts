import { describe, expect, it } from 'vitest'

import { lastDataAt, silentFor, silentRows } from '@/system/freshness'

const row = (scanner: string, silent: number | null) => ({
  scanner,
  last_ingest_at: silent === null ? null : '2026-07-08T21:06:28.782Z',
  silent_for_seconds: silent,
})

describe('freshness banner view-model (D20)', () => {
  it('filters to scanners past the window; null silence never fires', () => {
    const rows = [
      row('trivy', 2 * 24 * 3600), // fresh enough
      row('grype', 4 * 24 * 3600), // stale
      row('never', null),
    ]
    expect(silentRows(rows, 3 * 24 * 3600).map((r) => r.scanner)).toEqual(['grype'])
  })

  it('renders the silence as a coarse urgency duration', () => {
    expect(silentFor(4 * 86_400 + 3600)).toBe('4 days')
    expect(silentFor(86_400)).toBe('1 day')
    expect(silentFor(23 * 3600)).toBe('23 hours')
  })

  it('formats last-data time on the app-wide 24h convention (never AM/PM)', () => {
    const label = lastDataAt('2026-07-08T21:06:28.782Z')
    expect(label).not.toMatch(/AM|PM/i)
    expect(label).toMatch(/Jul/)
    expect(lastDataAt(null)).toBe('never')
  })
})
