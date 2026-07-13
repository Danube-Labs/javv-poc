/**
 * Approvals screen filter config (M9d slice 4b) — the prototype rail's dims (status,
 * approver, search) + the scanner column's value, all served by GET /decisions/approvals
 * (server-side; the endpoint's facets block feeds the counts). Same grammar as
 * AUDIT_FIELDS: one config drives FacetRail + FilterBar + URL sync.
 */
import type { FilterField } from '@/filters/fields.config'

/** the ExpiryChip vocabulary — status is derived server-side from expiry vs warn_days */
export const APPROVAL_STATUSES = ['expired', 'expiring', 'active', 'open-ended'] as const

export const APPROVAL_FIELDS: readonly FilterField[] = [
  // CVE contains-search (escaped wildcard server-side, the findings-q discipline)
  { key: 'q', label: 'Search', type: 'text', param: 'q', minLength: 2 },
  { key: 'status', label: 'Status', type: 'terms', param: 'status', facetKey: 'status', values: APPROVAL_STATUSES },
  { key: 'scanner', label: 'Scanner', type: 'terms', param: 'scanner', facetKey: 'scanner', values: ['both', 'trivy', 'grype'] },
  // data-driven from the facet buckets (exact keyword term)
  { key: 'approver', label: 'Approver', type: 'terms', param: 'created_by', facetKey: 'created_by' },
]
