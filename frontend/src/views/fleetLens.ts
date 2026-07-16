/**
 * Pure lens helpers shared by AllClustersView and its FleetTable panel (issue 384 split) —
 * a cluster row's server bucket count under the scanner lens is the by_scanner split,
 * never a client re-aggregation.
 */
import type { ClusterRow } from '@/stores/allClusters'
import type { Severity } from '@/styles/tokens'

export type ScannerLens = 'all' | 'trivy' | 'grype'

export function bucketCount(
  row: ClusterRow,
  facet: string,
  key: string,
  scanner: ScannerLens,
): number {
  const b = row.facets[facet]?.find((x) => x.key === key)
  if (!b) return 0
  return scanner === 'all' ? b.count : (b.by_scanner[scanner] ?? 0)
}

export const sevCount = (row: ClusterRow, sev: Severity, scanner: ScannerLens) =>
  bucketCount(row, 'severity', sev, scanner)

export const fmt = (n: number) => n.toLocaleString('en-US')
