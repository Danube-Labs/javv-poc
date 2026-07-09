/**
 * The togglable findings-grid columns — ONE list drives both the table's `v-if`s and the
 * Columns menu (same one-config-drives-both discipline as the filter module). Vulnerability,
 * Severity and State are fixed and not listed: a findings grid without them is meaningless.
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
  ['assignee', 'Assignee'],
] as const

export type FindingsColumnKey = (typeof FINDINGS_COLUMNS)[number][0]
