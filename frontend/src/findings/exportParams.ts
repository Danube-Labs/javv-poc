/** Pure builders for the export dialog (audit F-07/F-08): the scheduled export carries the
 * COMPLETE visible lens — every ExportParams field the backend contract knows — and a lens
 * key the contract can't represent blocks scheduling loudly, never silently widening the
 * export. Kept in sync with backend `reports/models.ExportParams` (the contract-gate regen
 * catches drift). */

export const EXPORT_PARAM_KEYS = [
  'severity', 'state', 'scanner', 'assignee', 'kev', 'fixable', 'disagree', 'cve_id',
  'image_digest', 'image_repo', 'namespace', 'ptype', 'q', 'present', 'new_within_days',
  'overdue', 'exclude_severity', 'exclude_state', 'exclude_scanner', 'exclude_assignee',
  'exclude_image_repo', 'exclude_namespace', 'exclude_ptype',
] as const

const GLOBAL_KEYS = new Set(['cluster_id', 'as_of', 'window_days'])

/** Lens keys the schedule contract cannot carry (globals excluded). Non-empty = block. */
export function unrepresentableKeys(lensQuery: Record<string, unknown>): string[] {
  return Object.keys(lensQuery).filter(
    (k) => !GLOBAL_KEYS.has(k) && !(EXPORT_PARAM_KEYS as readonly string[]).includes(k),
  )
}

/** The ExportParams blob for one schedule: whole lens + format; VEX pins its one scanner. */
export function scheduleParams(
  lensQuery: Record<string, unknown>,
  format: 'csv' | 'vex',
  vexScanner: string,
): Record<string, unknown> {
  const params: Record<string, unknown> = {
    format: format === 'csv' ? 'csv' : 'openvex',
  }
  for (const key of EXPORT_PARAM_KEYS) {
    if (lensQuery[key] !== undefined) params[key] = lensQuery[key]
  }
  if (format === 'vex') params.scanner = vexScanner // one scanner per VEX file (sacred)
  return params
}
