/**
 * The one `fields` config that drives BOTH FacetRail and FilterBar (PLAN gate: adding a field
 * here surfaces it in both with no component edits). Shape mirrors the backend contract, not
 * the prototype: only `severity`/`state` are multi-value params; `scanner`/`ptype`/`namespace`/
 * `image_repo`/`assignee` are single-valued; KEV / fix-available / disagree are boolean flags
 * (grouped as one "Attribute" facet, as in the prototype).
 */
import { SEVERITIES } from '@/styles/tokens'

interface BaseField {
  key: string
  label: string
}

/** Enumerated values → one query param. `multi` only where the backend accepts an array. */
export interface TermsField extends BaseField {
  type: 'terms'
  param: string
  multi?: boolean
  /** Field name in the facets response; omit for fields with no aggregation. */
  facetKey?: string
  /** Static vocabulary; omit to take values from the facet buckets. */
  values?: readonly string[]
}

/** A group of independent boolean params rendered as one facet group. */
export interface FlagsField extends BaseField {
  type: 'flags'
  values: readonly { key: string; param: string; label: string }[]
}

/** Free-text single-value param (no facet buckets). */
export interface TextField extends BaseField {
  type: 'text'
  param: string
}

export type FilterField = TermsField | FlagsField | TextField

/** Active selections, keyed by field key. Text fields hold a single-entry array. */
export type Selections = Record<string, string[]>

export const emptySelections = (fields: readonly FilterField[]): Selections =>
  Object.fromEntries(fields.map((f) => [f.key, []]))

/** Findings screen config (FR-12). Owned here; M9b+ screens import, never copy. */
export const FINDINGS_FIELDS: readonly FilterField[] = [
  { key: 'severity', label: 'Severity', type: 'terms', param: 'severity', multi: true, facetKey: 'severity', values: SEVERITIES },
  { key: 'scanner', label: 'Scanner', type: 'terms', param: 'scanner', facetKey: 'scanner', values: ['trivy', 'grype'] },
  {
    key: 'attr',
    label: 'Attribute',
    type: 'flags',
    values: [
      { key: 'kev', param: 'kev', label: 'KEV' },
      { key: 'fixable', param: 'fixable', label: 'Fix available' },
      { key: 'disagree', param: 'disagree', label: 'Scanners disagree' },
    ],
  },
  { key: 'state', label: 'State', type: 'terms', param: 'state', multi: true, facetKey: 'state', values: ['open', 'stale', 'acknowledged', 'resolved'] },
  { key: 'ptype', label: 'Package type', type: 'terms', param: 'ptype', facetKey: 'ptype' },
  { key: 'namespace', label: 'Namespace', type: 'text', param: 'namespace' },
  { key: 'image', label: 'Image', type: 'text', param: 'image_repo' },
  { key: 'assignee', label: 'Assignee', type: 'text', param: 'assignee' },
]
