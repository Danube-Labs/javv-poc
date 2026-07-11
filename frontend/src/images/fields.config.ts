/** Running-images filter config (M9c slice 3) — drives the M9a FacetRail + FilterBar exactly
 * like FINDINGS_FIELDS drives the findings screen (the module is imported, never re-built).
 * The inventory is one committed run's rows, already fully on the client — matching happens
 * over those served rows (pure, unit-tested in imageFilters.ts), so bucket counts are IMAGE
 * counts, not finding counts. No `app` field exists on the docs (data-first). */
import type { FilterField } from '@/filters/fields.config'
import { SEVERITIES } from '@/styles/tokens'

/** Columns menu vocabulary (Image + Findings stay fixed, like cve/severity/state in findings). */
export const IMAGES_COLUMNS = [
  ['tag', 'Tag'],
  ['namespace', 'Namespace'],
  ['replicas', 'Replicas'],
  ['mix', 'Severity mix'],
  ['seen', 'Last seen'],
] as const

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
