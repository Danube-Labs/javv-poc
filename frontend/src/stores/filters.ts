/**
 * Filter-selection store factory: one store instance per screen (findings, audit, images…),
 * all sharing this logic — selections keyed by the screen's `fields` config, serialized
 * to/from the route query so filtered views are shareable URLs (bolt M9a).
 *
 * URL format: one query param per field key, values comma-joined (`?severity=critical,high`).
 * Field keys never collide with the global params (`cluster_id` lives in the store, `as_of`
 * under its own key).
 *
 * Negation (issue 349): a NEGATABLE terms field carries a per-field mode — `is` (include,
 * the default) or `not` (exclude). The URL spells `not` as a `!` prefix on every value
 * (`?severity=!low,!negligible`); a field is one mode or the other, never mixed.
 */
import { defineStore } from 'pinia'
import type { LocationQuery } from 'vue-router'

import { emptySelections, type FilterField, type Selections } from '@/filters/fields.config'

export type FilterMode = 'is' | 'not'
export type Modes = Record<string, FilterMode>

export function makeFiltersStore(storeId: string, fields: readonly FilterField[]) {
  return defineStore(storeId, {
    state: () => ({ selections: emptySelections(fields) as Selections, modes: {} as Modes }),
    getters: {
      hasFilters: (s) => Object.values(s.selections).some((v) => v.length > 0),
      activeFields: (s) => fields.filter((f) => (s.selections[f.key] ?? []).length > 0),
      modeOf: (s) => (fieldKey: string) => s.modes[fieldKey] ?? 'is',
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
        delete this.modes[fieldKey]
      },
      clearAll() {
        this.selections = emptySelections(fields)
        this.modes = {}
      },
      setMode(fieldKey: string, mode: FilterMode) {
        const field = fields.find((f) => f.key === fieldKey)
        if (!field || field.type !== 'terms' || !field.negatable) return
        if (mode === 'is') delete this.modes[fieldKey]
        else this.modes[fieldKey] = mode
      },
      toggleMode(fieldKey: string) {
        this.setMode(fieldKey, (this.modes[fieldKey] ?? 'is') === 'is' ? 'not' : 'is')
      },
      /** Route query → selections (unknown keys and unknown vocabulary values are dropped). */
      fromQuery(query: LocationQuery) {
        const next = emptySelections(fields)
        const nextModes: Modes = {}
        for (const field of fields) {
          const raw = query[field.key]
          if (typeof raw !== 'string' || raw === '') continue
          let values = raw.split(',').filter(Boolean)
          if (field.type === 'terms' && field.negatable && values.some((v) => v.startsWith('!'))) {
            // any `!` flips the whole field to exclude (one mode per field, never mixed)
            nextModes[field.key] = 'not'
            values = values.map((v) => (v.startsWith('!') ? v.slice(1) : v)).filter(Boolean)
          }
          if (field.type === 'text') {
            // a shared URL can carry under-minLength text — drop it here so the chip never
            // shows a filter the builder refuses to emit (contract-guard, audit 343)
            const min = field.minLength ?? 1
            next[field.key] = values.slice(0, 1).filter((v) => v.trim().length >= min)
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
        this.modes = nextModes
      },
      /** Selections → route query fragment (empty fields omitted; excluded fields `!`-prefix
       * every value). */
      toQuery(): Record<string, string> {
        const query: Record<string, string> = {}
        for (const field of fields) {
          const values = this.selections[field.key] ?? []
          if (values.length === 0) continue
          const not = (this.modes[field.key] ?? 'is') === 'not'
          query[field.key] = values.map((v) => (not ? `!${v}` : v)).join(',')
        }
        return query
      },
    },
  })
}
