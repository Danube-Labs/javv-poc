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
import type { Modes } from '@/stores/filters'

export interface FilterGlobals {
  cluster_id: string
  as_of?: string
  /** The picker's trend window — consumed ONLY by `window` flags ("new in range"). */
  window_days?: number
}

export type FilterQuery = Record<string, string | string[] | boolean | number>

export function buildFilterQuery(
  fields: readonly FilterField[],
  selections: Selections,
  globals: FilterGlobals,
  modes: Modes = {},
): FilterQuery {
  if (!globals.cluster_id) throw new Error('buildFilterQuery: cluster_id is required on every query')

  const query: FilterQuery = { cluster_id: globals.cluster_id }
  if (globals.as_of !== undefined) query.as_of = globals.as_of

  for (const field of fields) {
    const selected = selections[field.key] ?? []
    if (selected.length === 0) continue

    if (field.type === 'terms') {
      const values = selected.map((v) => v.toLowerCase())
      // exclude mode (issue 349): the API mirror param, only on fields that declare one
      const param =
        field.negatable && (modes[field.key] ?? 'is') === 'not'
          ? `exclude_${field.param}`
          : field.param
      if (field.multi) {
        query[param] = values
      } else {
        if (values.length > 1)
          throw new Error(`buildFilterQuery: '${field.key}' accepts a single value, got ${values.length}`)
        query[param] = values[0] as string
      }
    } else if (field.type === 'flags') {
      for (const flag of field.values) {
        if (!selected.includes(flag.key)) continue
        if (flag.window) {
          if (globals.window_days === undefined)
            throw new Error(`buildFilterQuery: '${flag.key}' needs window_days in globals`)
          // the API's day-grained 1..365 contract, same rounding as the trend charts
          query[flag.param] = Math.min(365, Math.max(1, Math.ceil(globals.window_days)))
        } else {
          query[flag.param] = true
        }
      }
    } else {
      // under-minLength text is OMITTED, never sent — the API would 422 it; the input layer
      // owns the user feedback (contract-guard, audit 343)
      const text = (selected[0] ?? '').trim()
      if (text && text.length >= (field.minLength ?? 1)) query[field.param] = text
    }
  }

  return query
}
