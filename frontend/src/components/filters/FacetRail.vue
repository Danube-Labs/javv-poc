<script setup lang="ts">
/**
 * Left facet rail (prototype filters.jsx `FacetRail`/`FacetGroup` + `.facet-*` CSS). Renders
 * every listable field from the SAME config the FilterBar uses — one config drives both.
 * Counts come from the server's facets response verbatim; the per-scanner split is shown as a
 * tooltip and never combined client-side (FR-12).
 */
import { computed } from 'vue'

import { facetItems, scannerSplit, type FacetsResponse } from '@/filters/facets'
import type { FilterField, Selections } from '@/filters/fields.config'

const props = defineProps<{
  fields: readonly FilterField[]
  selections: Selections
  facets: FacetsResponse
}>()

const emit = defineEmits<{ toggle: [fieldKey: string, value: string] }>()

const groups = computed(() =>
  props.fields
    .map((field) => ({ field, items: facetItems(field, props.facets) }))
    .filter((g): g is { field: FilterField; items: NonNullable<typeof g.items> } => g.items !== null),
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
        :class="{ 'facet-on': (selections[g.field.key] ?? []).includes(it.value) }"
        :title="scannerSplit(it.byScanner)"
        @click="emit('toggle', g.field.key, it.value)"
      >
        <span class="facet-check" />
        <span class="facet-label">
          <slot name="value" :field="g.field" :value="it.value" :label="it.label">{{ it.label }}</slot>
        </span>
        <span v-if="it.count !== null" class="facet-count">{{ fmt(it.count) }}</span>
      </button>
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
