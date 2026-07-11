/** Running-images filter config (M9c slice 3) — drives the M9a FacetRail + FilterBar exactly
 * like FINDINGS_FIELDS drives the findings screen (the module is imported, never re-built).
 * The inventory is one committed run's rows, already fully on the client — matching happens
 * over those served rows (pure, unit-tested in imageFilters.ts), so bucket counts are IMAGE
 * counts, not finding counts. No `app` field exists on the docs (data-first). */
import type { FilterField } from '@/filters/fields.config'
import { SEVERITIES } from '@/styles/tokens'

/** Columns menu vocabulary — only Image stays fixed (row identity; pins are identity-only,
 * operator 2026-07-11); everything else moves and toggles, same as the findings grid. */
export const IMAGES_COLUMNS = [
  ['tag', 'Tag'],
  ['namespace', 'Namespace'],
  ['replicas', 'Replicas'],
  ['vulns', 'Vulns'],
  ['mixTrivy', 'Mix · trivy'],
  ['mixGrype', 'Mix · grype'],
  ['seen', 'Last seen'],
] as const

export type ImagesColumnKey = (typeof IMAGES_COLUMNS)[number][0]

export const IMAGES_FIELDS: readonly FilterField[] = [
  // the rail search box — CONTAINS across repo/tag/namespaces
  { key: 'q', label: 'Search', type: 'text', param: 'q' },
  {
    key: 'severity',
    label: 'Severity',
    type: 'terms',
    param: 'severity',
    multi: true,
    facetKey: 'severity',
    values: SEVERITIES,
  },
  {
    key: 'scanner',
    label: 'Scanner',
    type: 'terms',
    param: 'scanner',
    facetKey: 'scanner',
    values: ['trivy', 'grype'],
  },
  {
    key: 'attr',
    label: 'Attribute',
    type: 'flags',
    values: [{ key: 'fixable', param: 'fixable', label: 'Fix available' }],
  },
  { key: 'namespace', label: 'Namespace', type: 'terms', param: 'namespace', facetKey: 'namespaces' },
]
