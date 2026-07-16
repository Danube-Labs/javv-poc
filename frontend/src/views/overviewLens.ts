/**
 * Pure lens helpers shared by OverviewView and its extracted panels (issue 384 split) — a
 * bucket's display count under the scanner lens is the server's by_scanner split, never a
 * client re-aggregation.
 */
import type { FacetBucket } from '@/stores/overview'

export type ScannerLens = 'all' | 'trivy' | 'grype'

export function countOf(bucket: FacetBucket | null, scanner: ScannerLens): number {
  if (!bucket) return 0
  return scanner === 'all' ? bucket.count : (bucket.by_scanner[scanner] ?? 0)
}

export const fmt = (n: number) => n.toLocaleString('en-US')
