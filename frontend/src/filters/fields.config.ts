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
  /** The backend has an `exclude_<param>` mirror (issue 349) — the bar offers is/is not and
   * the URL carries `!`-prefixed values. Only findings fields today. */
  negatable?: boolean
}

/** A group of independent boolean params rendered as one facet group. A `window` flag emits
 * the picker's trend-window days instead of `true` — the "new in range" event lens. */
export interface FlagsField extends BaseField {
  type: 'flags'
  values: readonly {
    key: string
    param: string
    label: string
    window?: boolean
    /** Hover explanation for non-obvious flags (rail row title). */
    hint?: string
  }[]
}

/** Free-text single-value param (no facet buckets). `minLength` mirrors the API's own
 * validation — a keystroke must never emit a known-invalid query (contract-guard, audit 343). */
export interface TextField extends BaseField {
  type: 'text'
  param: string
  minLength?: number
  /** Same `exclude_<param>` mirror as a terms field. A text field can carry it because some
   * of these params are EXACT terms server-side (`image_repo` is a `term` clause, not a
   * wildcard) — the free-text input is just the entry affordance, not the match semantics. */
  negatable?: boolean
}

export type FilterField = TermsField | FlagsField | TextField

/** Does this field have an `exclude_<param>` twin to negate into? Flags never do — absence
 * and negation are different questions (issue 349 §1). One helper so the six places that ask
 * cannot drift apart. */
export const isNegatable = (field: FilterField): boolean =>
  field.type !== 'flags' && field.negatable === true

/** Active selections, keyed by field key. Text fields hold a single-entry array. */
export type Selections = Record<string, string[]>

export const emptySelections = (fields: readonly FilterField[]): Selections =>
  Object.fromEntries(fields.map((f) => [f.key, []]))

/** Findings screen config (FR-12). Owned here; M9b+ screens import, never copy. */
export const FINDINGS_FIELDS: readonly FilterField[] = [
  // the rail search box writes this — CONTAINS across cve/image/namespace/assignee/package
  { key: 'q', label: 'Search', type: 'text', param: 'q', minLength: 2 },
  { key: 'severity', label: 'Severity', type: 'terms', param: 'severity', multi: true, facetKey: 'severity', values: SEVERITIES, negatable: true },
  { key: 'scanner', label: 'Scanner', type: 'terms', param: 'scanner', facetKey: 'scanner', values: ['trivy', 'grype'], negatable: true },
  {
    key: 'attr',
    label: 'Attribute',
    type: 'flags',
    values: [
      { key: 'kev', param: 'kev', label: 'KEV' },
      { key: 'fixable', param: 'fixable', label: 'Fix available' },
      { key: 'disagree', param: 'disagree', label: 'Scanners disagree' },
      // issue 363: ranges on the materialized D21 group clock against the LIVE SLA policy —
      // exactly the rows whose SLA cell reads overdue (chip ≡ filter, pinned server-side)
      {
        key: 'overdue',
        param: 'overdue',
        label: 'SLA breached',
        hint:
          'Findings past their SLA deadline under the current policy — the same rows whose ' +
          'SLA column shows overdue. Handled findings (risk-accepted, not-affected, resolved) ' +
          'are never counted.',
      },
      {
        key: 'unassigned',
        param: 'unassigned',
        label: 'Unassigned',
        hint:
          'Findings nobody owns yet — the untriaged backlog. This is absence, not exclusion: ' +
          '"assignee is not <someone>" keeps unowned rows too, so it can never ask this.',
      },
      // first_seen_at within the global range — the event view of the state table
      {
        key: 'new',
        param: 'new_within_days',
        label: 'New in range',
        window: true,
        hint:
          'Only findings first seen inside the selected time range — a quiet range shows 0. ' +
          'Off, the table shows everything currently present.',
      },
    ],
  },
  { key: 'state', label: 'State', type: 'terms', param: 'state', multi: true, facetKey: 'state', values: ['open', 'acknowledged', 'not_affected', 'risk_accepted', 'resolved', 'stale'], negatable: true },
  { key: 'ptype', label: 'Package type', type: 'terms', param: 'ptype', facetKey: 'ptype', negatable: true },
  // rail dims are top-N by count (server caps at 32); the value-search in Add-filter still
  // reaches anything the rail's cap hides
  { key: 'namespace', label: 'Namespace', type: 'terms', param: 'namespace', facetKey: 'namespaces', negatable: true },
  // `image_repo` is an exact `term` server-side, so the grid's image cell can filter on the
  // row's FULL repo — and negate it, since `exclude_image_repo` exists (issue 349 §2)
  { key: 'image', label: 'Image', type: 'text', param: 'image_repo', negatable: true },
  { key: 'assignee', label: 'Assignee', type: 'terms', param: 'assignee', facetKey: 'assignee', negatable: true },
]
