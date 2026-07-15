/** M9e slice 4 — the Data & OpenSearch pure form module (parsing, dirty groups, row-23 family
 * registry) + the live staleness threshold plumbing the banner rewire introduced. */
import { describe, expect, it } from 'vitest'

import {
  changedGroups,
  draftDirty,
  draftFromKnobs,
  draftInvalid,
  FAMILY_ROWS,
  parseCount,
  parseDraft,
  type DataKnobs,
} from '@/views/settings/dataForm'
import { D20_FRESHNESS_DEFAULT_S, freshnessStatus, silentRows } from '@/system/freshness'

const SAVED: DataKnobs = {
  retention_days: 90,
  max_age_days: 30,
  max_docs: 5_000_000,
  max_size_gb: 50,
  cleanup_days: 180,
  report_ttl_hours: 24,
}

describe('dataForm parsing', () => {
  it('parseCount takes positive integers only', () => {
    expect(parseCount('24')).toBe(24)
    expect(parseCount(' 5000000 ')).toBe(5_000_000)
    expect(parseCount('0')).toBeNull()
    expect(parseCount('-3')).toBeNull()
    expect(parseCount('1.5')).toBeNull()
    expect(parseCount('1e3')).toBeNull()
    expect(parseCount('')).toBeNull()
    expect(parseCount('abc')).toBeNull()
  })

  it('round-trips knobs → draft → parsed unchanged', () => {
    const draft = draftFromKnobs(SAVED)
    expect(parseDraft(draft)).toEqual(SAVED)
    expect(draftInvalid(draft)).toBe(false)
    expect(draftDirty(SAVED, draft)).toBe(false)
  })

  it('flags the one invalid field without failing the rest', () => {
    const draft = { ...draftFromKnobs(SAVED), maxDocs: 'many' }
    const parsed = parseDraft(draft)
    expect(parsed.max_docs).toBeNull()
    expect(parsed.retention_days).toBe(90)
    expect(draftInvalid(draft)).toBe(true)
  })

  it('a re-typed identical value is NOT dirty (semantic compare)', () => {
    const draft = { ...draftFromKnobs(SAVED), retention: '90.0' }
    expect(draftDirty(SAVED, draft)).toBe(false)
  })
})

describe('changedGroups (save PUTs only what changed)', () => {
  it('clean draft → no groups', () => {
    expect(changedGroups(SAVED, draftFromKnobs(SAVED))).toEqual({
      retention: false,
      rollover: false,
      cleanup: false,
      ttl: false,
    })
  })

  it('one rollover field marks only the rollover group', () => {
    const draft = { ...draftFromKnobs(SAVED), maxDocs: '1000' }
    expect(changedGroups(SAVED, draft)).toEqual({
      retention: false,
      rollover: true,
      cleanup: false,
      ttl: false,
    })
  })

  it('retention + ttl edits mark exactly those groups', () => {
    const draft = { ...draftFromKnobs(SAVED), retention: '45', ttl: '48' }
    expect(changedGroups(SAVED, draft)).toEqual({
      retention: true,
      rollover: false,
      cleanup: false,
      ttl: true,
    })
  })
})

describe('the row-23 family registry', () => {
  it('lists exactly the four append families sharing the window', () => {
    const append = FAMILY_ROWS.filter((f) => f.kind === 'append').map((f) => f.pattern)
    expect(append).toEqual([
      'javv-finding-occurrences-*',
      'javv-scan-events-*',
      'javv-images-*',
      'javv-inventory-runs-*',
    ])
  })

  it('every protected family carries its why', () => {
    for (const f of FAMILY_ROWS.filter((x) => x.kind === 'protected')) {
      expect.soft(f.why).toBeTruthy()
    }
    // the D45 order counter and the audit journal must never gain a retention control
    const patterns = FAMILY_ROWS.filter((x) => x.kind === 'protected').map((f) => f.pattern)
    expect(patterns).toContain('javv-scan-orders')
    expect(patterns).toContain('system-audit-log-*')
    expect(patterns).toContain('findings')
  })
})

describe('live staleness threshold (banner rewire)', () => {
  const rows = [
    { scanner: 'trivy', last_ingest_at: '2026-07-15T00:00:00Z', silent_for_seconds: 2 * 86_400 },
    { scanner: 'grype', last_ingest_at: '2026-07-10T00:00:00Z', silent_for_seconds: 6 * 86_400 },
  ]

  it('defaults to the D20 seed (3 days) while the live read is in flight', () => {
    expect(D20_FRESHNESS_DEFAULT_S).toBe(3 * 24 * 3600)
    expect(silentRows(rows).map((r) => r.scanner)).toEqual(['grype'])
  })

  it('an operator-tightened window flips the verdict — the build-time constant could not', () => {
    expect(freshnessStatus(rows, 1 * 86_400)).toBe('stale')
    expect(silentRows(rows, 1 * 86_400)).toHaveLength(2)
    expect(freshnessStatus(rows, 7 * 86_400)).toBe('ok')
  })
})
