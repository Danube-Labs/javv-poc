/**
 * Pure view-model for the finding detail screen (M9b slice 2). Per-scanner is sacred: nothing
 * here merges, reconciles, or sums across scanners — it only orders rows, compares them, and
 * flags disagreement. KEV/EPSS are grype-only enrichments (INDEX-MAP), so the header surfaces
 * them from whichever row carries them, labeled with the source scanner. Historical (`as_of`)
 * rows null-out unattested fields — every function tolerates nulls.
 */
import type { FindingRow } from '@/stores/findings'

export const SCANNER_ORDER = ['trivy', 'grype'] as const

/** Evidence rows in fixed scanner order — verbatim rows, never merged. */
export function orderEvidence(rows: FindingRow[]): FindingRow[] {
  const rank = (s: string) => {
    const i = (SCANNER_ORDER as readonly string[]).indexOf(s)
    return i === -1 ? SCANNER_ORDER.length : i
  }
  return [...rows].sort((a, b) => rank(a.scanner) - rank(b.scanner))
}

/** True when the pair disagrees on canonical severity, or a row's precomputed flag says so. */
export function severityDisagrees(rows: FindingRow[]): boolean {
  if (rows.some((r) => r.disagree === true)) return true
  const canon = new Set(rows.map((r) => r.severity_canonical).filter(Boolean))
  return canon.size > 1
}

/** The header's primary row: the scanner the user clicked, else first in scanner order. */
export function primaryRow(rows: FindingRow[], preferredScanner?: string | null): FindingRow | null {
  if (rows.length === 0) return null
  return rows.find((r) => r.scanner === preferredScanner) ?? orderEvidence(rows)[0]!
}

/** KEV across the pair (grype-only field; null on historical rows). */
export function kevOn(rows: FindingRow[]): boolean {
  return rows.some((r) => r.kev === true)
}

/** The EPSS score + which scanner attested it, or null when no row carries one. */
export function epssOf(rows: FindingRow[]): { value: number; scanner: string } | null {
  const row = orderEvidence(rows).find((r) => typeof r.epss === 'number')
  return row ? { value: row.epss as number, scanner: row.scanner } : null
}

/** One "images affected" table row. Counts stay side-by-side — never summed. */
export interface ImageGroupRow {
  repo: string
  /** Per-scanner finding counts for this repo+CVE; null = the scanner reported nothing here. */
  trivy: number | null
  grype: number | null
  /** |trivy − grype| for display only (absent side counts as 0) — never a merged total. */
  delta: number
  /** One scanner at zero/absent while the other reports — disagreement-grade weight. */
  zeroVsNonzero: boolean
}

interface GroupBucket {
  key: string | number | boolean
  count: number
  by_scanner: Record<string, number>
}

export function imageGroupRows(buckets: GroupBucket[]): ImageGroupRow[] {
  return buckets.map((b) => {
    const trivy = b.by_scanner['trivy'] ?? null
    const grype = b.by_scanner['grype'] ?? null
    const t = trivy ?? 0
    const g = grype ?? 0
    return {
      repo: String(b.key),
      trivy,
      grype,
      delta: Math.abs(t - g),
      zeroVsNonzero: (t === 0) !== (g === 0),
    }
  })
}
