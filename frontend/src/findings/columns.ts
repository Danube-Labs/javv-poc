/**
 * The togglable findings-grid columns — ONE list drives both the table's `v-if`s and the
 * Columns menu (same one-config-drives-both discipline as the filter module). Only
 * Vulnerability and Severity are fixed and not listed (the row's identity); everything
 * else — State included (operator 2026-07-11) — moves and toggles freely.
 */
export const FINDINGS_COLUMNS = [
  ['epss', 'EPSS'],
  ['kev', 'KEV'],
  ['package', 'Package'],
  ['current', 'Current'],
  ['fixed', 'Fixed'],
  ['image', 'Image'],
  ['namespace', 'Namespace'],
  ['images', 'Affected images'],
  ['scanner', 'Scanner'],
  ['sla', 'SLA'],
  ['state', 'State'],
  ['assignee', 'Assignee'],
] as const

export type FindingsColumnKey = (typeof FINDINGS_COLUMNS)[number][0]
