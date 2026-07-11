/**
 * Shapes the M6 facets response for display. Both FacetRail and FilterBar list values through
 * `facetItems()`, so a field added to the config surfaces in both automatically (PLAN gate).
 *
 * Counts are passed through from the server verbatim — the per-scanner split is display data,
 * NEVER summed or otherwise combined client-side (FR-12, per-scanner sacred).
 */
import type { FilterField } from './fields.config'

export interface FacetBucket {
  key: string
  count: number
  by_scanner: Record<string, number>
}

export type FacetsResponse = Record<string, FacetBucket[]>

export interface FacetItem {
  value: string
  label: string
  /** Server-side count; null when the backend has no aggregation for this value. */
  count: number | null
  byScanner: Record<string, number> | null
  /** Config-declared hover explanation (flags only); wins over the scanner split. */
  hint?: string
}

const item = (value: string, label: string, bucket?: FacetBucket, hint?: string): FacetItem => ({
  value,
  label,
  count: bucket ? bucket.count : null,
  byScanner: bucket ? bucket.by_scanner : null,
  ...(hint !== undefined ? { hint } : {}),
})

/** Display items for one field, or null when the field has no listable values (text fields). */
export function facetItems(field: FilterField, facets: FacetsResponse): FacetItem[] | null {
  if (field.type === 'text') return null

  if (field.type === 'flags') {
    return field.values.map((flag) =>
      item(flag.key, flag.label, (facets[flag.param] ?? []).find((b) => b.key === 'true'), flag.hint),
    )
  }

  const buckets = field.facetKey ? (facets[field.facetKey] ?? []) : []
  if (field.values) {
    // static vocabulary: config order, counts filled in where the server aggregated
    return field.values.map((v) => item(v, v, buckets.find((b) => b.key === v)))
  }
  // dynamic vocabulary: the server's buckets, in server order
  return buckets.map((b) => item(b.key, b.key, b))
}

/** `trivy 791 · grype 854` — tooltip text for the per-scanner split. */
export function scannerSplit(byScanner: Record<string, number> | null): string {
  if (!byScanner) return ''
  return Object.entries(byScanner)
    .map(([scanner, count]) => `${scanner} ${count}`)
    .join(' · ')
}
