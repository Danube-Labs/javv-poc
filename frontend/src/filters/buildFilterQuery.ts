/**
 * Pure option-builder: fields config + active selections + globals → the exact query-param
 * object sent to the backend. The primary unit-tested surface (bolt M9a DoD):
 *   - `cluster_id` is ALWAYS present (tenant chokepoint — throws if missing);
 *   - `as_of` passes through only when time-traveling (T=now omits it, D28);
 *   - term values are lowercased (severity case-insensitive, D16);
 *   - single-value params never join/merge multiple selections — a second selection is a bug
 *     upstream and throws here rather than silently mangling the query.
 */
import type { FilterField, Selections } from './fields.config'

export interface FilterGlobals {
  cluster_id: string
  as_of?: string
}

export type FilterQuery = Record<string, string | string[] | boolean>

export function buildFilterQuery(
  fields: readonly FilterField[],
  selections: Selections,
  globals: FilterGlobals,
): FilterQuery {
  if (!globals.cluster_id) throw new Error('buildFilterQuery: cluster_id is required on every query')

  const query: FilterQuery = { cluster_id: globals.cluster_id }
  if (globals.as_of !== undefined) query.as_of = globals.as_of

  for (const field of fields) {
    const selected = selections[field.key] ?? []
    if (selected.length === 0) continue

    if (field.type === 'terms') {
      const values = selected.map((v) => v.toLowerCase())
      if (field.multi) {
        query[field.param] = values
      } else {
        if (values.length > 1)
          throw new Error(`buildFilterQuery: '${field.key}' accepts a single value, got ${values.length}`)
        query[field.param] = values[0] as string
      }
    } else if (field.type === 'flags') {
      for (const flag of field.values) {
        if (selected.includes(flag.key)) query[flag.param] = true
      }
    } else {
      const text = (selected[0] ?? '').trim()
      if (text) query[field.param] = text
    }
  }

  return query
}
