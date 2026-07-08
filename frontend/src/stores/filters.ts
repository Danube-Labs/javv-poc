/**
 * Filter-selection store factory: one store instance per screen (findings, audit, images…),
 * all sharing this logic — selections keyed by the screen's `fields` config, serialized
 * to/from the route query so filtered views are shareable URLs (bolt M9a).
 *
 * URL format: one query param per field key, values comma-joined (`?severity=critical,high`).
 * Field keys never collide with the global params (`cluster_id` lives in the store, `as_of`
 * under its own key).
 */
import { defineStore } from 'pinia'
import type { LocationQuery } from 'vue-router'

import { emptySelections, type FilterField, type Selections } from '@/filters/fields.config'

export function makeFiltersStore(storeId: string, fields: readonly FilterField[]) {
  return defineStore(storeId, {
    state: () => ({ selections: emptySelections(fields) as Selections }),
    getters: {
      hasFilters: (s) => Object.values(s.selections).some((v) => v.length > 0),
      activeFields: (s) => fields.filter((f) => (s.selections[f.key] ?? []).length > 0),
    },
    actions: {
      toggle(fieldKey: string, value: string) {
        const field = fields.find((f) => f.key === fieldKey)
        if (!field) return
        const current = this.selections[fieldKey] ?? []
        if (current.includes(value)) {
          this.selections[fieldKey] = current.filter((v) => v !== value)
        } else if (field.type === 'terms' && !field.multi) {
          this.selections[fieldKey] = [value] // single-value param: replace, never accumulate
        } else {
          this.selections[fieldKey] = [...current, value]
        }
      },
      setText(fieldKey: string, value: string) {
        this.selections[fieldKey] = value.trim() ? [value.trim()] : []
      },
      clearField(fieldKey: string) {
        this.selections[fieldKey] = []
      },
      clearAll() {
        this.selections = emptySelections(fields)
      },
      /** Route query → selections (unknown keys and unknown vocabulary values are dropped). */
      fromQuery(query: LocationQuery) {
        const next = emptySelections(fields)
        for (const field of fields) {
          const raw = query[field.key]
          if (typeof raw !== 'string' || raw === '') continue
          const values = raw.split(',').filter(Boolean)
          if (field.type === 'text') {
            next[field.key] = values.slice(0, 1)
          } else if (field.type === 'flags') {
            const known = new Set(field.values.map((v) => v.key))
            next[field.key] = values.filter((v) => known.has(v))
          } else if (field.values) {
            const known = new Set(field.values)
            const kept = values.filter((v) => known.has(v))
            next[field.key] = field.multi ? kept : kept.slice(0, 1)
          } else {
            next[field.key] = field.multi ? values : values.slice(0, 1)
          }
        }
        this.selections = next
      },
      /** Selections → route query fragment (empty fields omitted). */
      toQuery(): Record<string, string> {
        const query: Record<string, string> = {}
        for (const field of fields) {
          const values = this.selections[field.key] ?? []
          if (values.length > 0) query[field.key] = values.join(',')
        }
        return query
      },
    },
  })
}
