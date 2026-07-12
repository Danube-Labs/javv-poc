import { describe, expect, it } from 'vitest'

import { DB_AGE_WARN_AFTER_S, dbAgeSeconds, lastDataAt, silentFor, silentRows } from '@/system/freshness'

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

describe('vuln-DB age flag (M9d slice 2)', () => {
  const now = Date.parse('2026-07-12T12:00:00Z')

  it('ages a built stamp against now; unparseable/missing stays null (no claim)', () => {
    expect(dbAgeSeconds('2026-07-11T12:00:00Z', now)).toBe(86_400)
    expect(dbAgeSeconds(null, now)).toBeNull()
    expect(dbAgeSeconds('not-a-date', now)).toBeNull()
  })

  it('the default warn window is 7 days (VITE_DB_AGE_WARN_DAYS overrides at build)', () => {
    expect(DB_AGE_WARN_AFTER_S).toBe(7 * 86_400)
    expect(dbAgeSeconds('2026-07-03T12:00:00Z', now)! > DB_AGE_WARN_AFTER_S).toBe(true)
    expect(dbAgeSeconds('2026-07-08T12:00:00Z', now)! > DB_AGE_WARN_AFTER_S).toBe(false)
  })
})
