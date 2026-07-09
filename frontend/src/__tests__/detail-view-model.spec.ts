/**
 * The N10 contract for the detail screen: per-scanner rows are ordered and compared but NEVER
 * merged; KEV/EPSS surface with their source scanner; image count pairs stay side-by-side with
 * zero-vs-nonzero flagged at disagreement grade. Null-tolerant for historical rows.
 */
import { describe, expect, it } from 'vitest'

import {
  epssOf,
  imageGroupRows,
  kevOn,
  orderEvidence,
  primaryRow,
  scopeToPackage,
  severityDisagrees,
} from '@/findings/detailViewModel'
import type { FindingRow } from '@/stores/findings'

function row(over: Partial<FindingRow>): FindingRow {
  return {
    finding_key: 'k',
    cve_id: 'CVE-2024-0001',
    scanner: 'trivy',
    severity: 'HIGH',
    severity_canonical: 'high',
    image_repo: 'nginx',
    tag: '1.25',
    package_name: 'openssl',
    installed_version: '3.0.1',
    fixed_version: null,
    fixable: false,
    epss: null,
    kev: false,
    ptype: null,
    state: 'open',
    overdue: false,
    due_at: null,
    ...over,
  }
}

describe('detail view-model (per-scanner sacred)', () => {
  it('orders evidence trivy-first and keeps both rows verbatim — never merges', () => {
    const grype = row({ scanner: 'grype', severity: 'Critical', severity_canonical: 'critical' })
    const trivy = row({ scanner: 'trivy', severity: 'HIGH', severity_canonical: 'high' })
    const out = orderEvidence([grype, trivy])
    expect(out.map((r) => r.scanner)).toEqual(['trivy', 'grype'])
    expect(out[0]!.severity).toBe('HIGH') // verbatim, not reconciled
    expect(out[1]!.severity).toBe('Critical')
    expect(out).toHaveLength(2)
  })

  it('flags severity disagreement from the canonical pair or the precomputed flag', () => {
    const agree = [row({}), row({ scanner: 'grype' })]
    expect(severityDisagrees(agree)).toBe(false)
    const differ = [row({}), row({ scanner: 'grype', severity_canonical: 'critical' })]
    expect(severityDisagrees(differ)).toBe(true)
    const flagged = [row({ disagree: true }), row({ scanner: 'grype', disagree: true })]
    expect(severityDisagrees(flagged)).toBe(true)
  })

  it('primary row honors the clicked scanner and falls back to scanner order', () => {
    const rows = [row({}), row({ scanner: 'grype' })]
    expect(primaryRow(rows, 'grype')?.scanner).toBe('grype')
    expect(primaryRow(rows, 'unknown-scanner')?.scanner).toBe('trivy')
    expect(primaryRow([], 'trivy')).toBeNull()
  })

  it('KEV/EPSS come from whichever row attests them — null-tolerant (historical rows)', () => {
    const historical = [
      row({ kev: null as unknown as boolean, epss: null }),
      row({ scanner: 'grype', kev: null as unknown as boolean, epss: null }),
    ]
    expect(kevOn(historical)).toBe(false)
    expect(epssOf(historical)).toBeNull()

    const enriched = [row({}), row({ scanner: 'grype', kev: true, epss: 0.53 })]
    expect(kevOn(enriched)).toBe(true)
    expect(epssOf(enriched)).toEqual({ value: 0.53, scanner: 'grype' })
  })

  it('scopes evidence to one package — the clicked one, or the first row on deep links', () => {
    const rows = [
      row({ finding_key: 'a', package_name: 'libcurl4', scanner: 'trivy' }),
      row({ finding_key: 'b', package_name: 'curl', scanner: 'trivy' }),
      row({ finding_key: 'c', package_name: 'libcurl4', scanner: 'grype' }),
      row({ finding_key: 'd', package_name: 'curl', scanner: 'grype' }),
    ]
    const clicked = scopeToPackage(rows, 'curl', '3.0.1')
    expect(clicked.scoped.map((r) => r.finding_key)).toEqual(['b', 'd'])
    expect(clicked.otherPackages).toEqual(['libcurl4'])

    const deepLink = scopeToPackage(rows, null)
    expect(deepLink.scoped.map((r) => r.package_name)).toEqual(['libcurl4', 'libcurl4'])
    expect(scopeToPackage([], 'curl').scoped).toEqual([])
  })

  it('image groups keep per-scanner counts side-by-side; zero-vs-nonzero gets the flag', () => {
    const rows = imageGroupRows([
      { key: 'nginx', count: 8, by_scanner: { trivy: 4, grype: 4 } },
      { key: 'alpine', count: 73, by_scanner: { grype: 73 } }, // trivy silent — real-scanner divergence can be total
      { key: 'redis', count: 5, by_scanner: { trivy: 3, grype: 2 } },
    ])
    // display order is worst-first (highest per-scanner count) so 100+ images stays scannable
    expect(rows.map((r) => r.repo)).toEqual(['alpine', 'nginx', 'redis'])
    expect(rows[0]).toMatchObject({ repo: 'alpine', trivy: null, grype: 73, delta: 73, zeroVsNonzero: true })
    expect(rows[1]).toMatchObject({ repo: 'nginx', trivy: 4, grype: 4, delta: 0, zeroVsNonzero: false })
    expect(rows[2]).toMatchObject({ repo: 'redis', delta: 1, zeroVsNonzero: false })
    // no row ever exposes a summed total
    for (const r of rows) expect(Object.keys(r)).not.toContain('total')
  })
})
