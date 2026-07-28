<script setup lang="ts">
/**
 * Left facet rail (prototype filters.jsx `FacetRail`/`FacetGroup` + `.facet-*` CSS). Renders
 * every listable field from the SAME config the FilterBar uses — one config drives both.
 * Counts come from the server's facets response verbatim; the per-scanner split is shown as a
 * tooltip and never combined client-side (FR-12).
 */
import { computed } from 'vue'

import ValueActions from '@/components/filters/ValueActions.vue'
import { facetItems, scannerSplit, type FacetsResponse } from '@/filters/facets'
import type { FilterField, Selections } from '@/filters/fields.config'
import type { FilterMode, Modes } from '@/stores/filters'

const props = defineProps<{
  fields: readonly FilterField[]
  selections: Selections
  facets: FacetsResponse
  modes?: Modes
}>()

const emit = defineEmits<{
  toggle: [fieldKey: string, value: string]
  pick: [fieldKey: string, value: string, mode: FilterMode]
}>()

/** Exclude is offered only where the backend has an `exclude_*` twin to receive it. */
const negatable = (field: FilterField) => field.type === 'terms' && field.negatable === true

/** The mode this value is selected under, or null when it is not selected at all. */
function activeMode(field: FilterField, value: string): FilterMode | null {
  if (!(props.selections[field.key] ?? []).includes(value)) return null
  return props.modes?.[field.key] ?? 'is'
}

const groups = computed(() =>
  props.fields
    .map((field) => ({ field, items: facetItems(field, props.facets) }))
    .filter((g): g is { field: FilterField; items: NonNullable<typeof g.items> } => g.items !== null)
    // data-driven sections (no fixed vocabulary) hide until they HAVE buckets — a bare header
    // over nothing reads as broken on a first-run cluster
    .filter((g) => g.items.length > 0 || ('values' in g.field && g.field.values !== undefined)),
)

const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <aside class="facets" aria-label="Filters">
    <slot name="header" />
    <div v-for="g in groups" :key="g.field.key" class="facet">
      <div class="facet-title">{{ g.field.label }}</div>
      <button
        v-for="it in g.items"
        :key="it.value"
        class="facet-row"
        :class="{
          'facet-on': activeMode(g.field, it.value) === 'is',
          'facet-out': activeMode(g.field, it.value) === 'not',
        }"
        :title="it.hint ?? scannerSplit(it.byScanner)"
        @click="emit('toggle', g.field.key, it.value)"
      >
        <span class="facet-check" />
        <span class="facet-label">
          <slot name="value" :field="g.field" :value="it.value" :label="it.label">{{ it.label }}</slot>
        </span>
        <span v-if="it.count !== null" class="facet-count">{{ fmt(it.count) }}</span>
        <!-- the row click already means include, so the action offers the other side only -->
        <ValueActions
          v-if="negatable(g.field)"
          class="val-act-reveal"
          exclude-only
          :field="g.field.label"
          :value="it.value"
          :active="activeMode(g.field, it.value)"
          @pick="(m) => emit('pick', g.field.key, it.value, m)"
        />
      </button>
      <p v-if="g.items.length >= 32" class="facet-cap">top 32 by count; search reaches the rest</p>
    </div>
  </aside>
</template>

<style scoped>
.facets {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  padding: 6px;
  box-shadow: var(--shadow);
  position: sticky;
  top: 0;
  width: var(--facet-rail-w);
  flex: none;
}
.facet {
  padding: 8px 4px;
  border-top: 1px solid var(--line2);
}
.facet:first-of-type {
  border-top: 0;
}
.facet-title {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--soft);
  padding: 2px 8px 8px;
  font-weight: 700;
}
.facet-cap {
  margin: 4px 8px 2px;
  font-size: var(--text-facet-count);
  font-family: var(--font-mono);
  color: var(--soft);
  line-height: 1.4;
}
.facet-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 5px 8px;
  border-radius: 7px;
  text-align: left;
  color: var(--ink);
  font-size: var(--text-control);
  cursor: default;
}
.facet-row:hover {
  background: var(--panel);
}
.facet-row:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.facet-check {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  border: 1.5px solid var(--facet-check-line);
  flex: none;
  transition: 0.1s;
}
.facet-on .facet-check {
  background: var(--coral);
  border-color: var(--coral);
  box-shadow: inset 0 0 0 2px var(--card);
}
.facet-on {
  color: var(--ink);
  font-weight: 500;
}
/* an excluded value stays listed and readable (operator ruling 2026-07-27) — struck, not
   hidden, so the operator can see what they ruled out and click it off again. The red is
   `--fpill-not-op`, the same exclusion language the NOT-pill carries. */
.facet-out .facet-label {
  text-decoration: line-through;
  text-decoration-color: var(--fpill-not-op);
  text-decoration-thickness: 1.5px;
  color: var(--soft);
}
.facet-out .facet-check {
  border-color: var(--fpill-not-op);
  background: transparent;
}
.facet-label {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
}
.facet-count {
  font-family: var(--font-mono);
  font-size: var(--text-facet-count);
  color: var(--soft);
}
</style>
