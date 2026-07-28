<script setup lang="ts">
/**
 * Include / exclude actions for ONE facet value (issue 349 §2) — the third part of the M9a
 * filter module, beside `FacetRail` and `FilterBar`. It sits wherever the operator meets a
 * value (a rail row, a grid cell) so "filter to this" and "filter this out" never require
 * opening the Add-filter picker first.
 *
 * Two things here are inherited, not invented:
 * - It renders SPANS, not buttons. Both hosts nest it inside a `<button>` (the rail's
 *   `.facet-row`; the picker's value rows) and a button may not contain a button — the
 *   prototype's own escape hatch for `.fpill-x`. Unlike `.fpill-x` it IS keyboard-operable.
 * - The glyphs are text, like `.fpill-x`'s literal `×`, so the ported AppIcon set stays
 *   verbatim (it has no `minus`, and inventing one would break "ported from the prototype").
 *
 * Deviation on record (DESIGN.md §8.4): the prototype's filter grammar is include-only, so
 * this affordance has no prototype source. Operator ruling 2026-07-27 chose the ⊕/⊖ pair over
 * a per-value dropdown. Its at-rest-vs-hover reveal is a HOST decision — the visual states
 * live in `base.css` beside `.cell-go` because they key off the host row's `:hover`.
 */
import type { FilterMode } from '@/stores/filters'

const props = defineProps<{
  /** Field label, spoken in the aria-label: "Filter out Namespace kube-system". */
  field: string
  /** The value these actions act on. */
  value: string
  /** The mode this value is already selected under — that side reads as pressed. */
  active?: FilterMode | null
  /** The host already owns include (the rail row's own click), so show exclude only. */
  excludeOnly?: boolean
}>()

const emit = defineEmits<{ pick: [mode: FilterMode] }>()

/** Clicking the side that is already active clears it — the same toggle the row/pill offer. */
const label = (mode: FilterMode) =>
  props.active === mode
    ? `Clear ${mode === 'not' ? 'exclusion of' : 'filter on'} ${props.field} ${props.value}`
    : `Filter ${mode === 'not' ? 'out' : 'to'} ${props.field} ${props.value}`
</script>

<template>
  <span class="val-act" @click.stop>
    <span
      v-if="!excludeOnly"
      class="val-act-btn"
      :class="{ 'val-act-on': active === 'is' }"
      role="button"
      tabindex="0"
      :aria-label="label('is')"
      :aria-pressed="active === 'is'"
      :title="label('is')"
      @click="emit('pick', 'is')"
      @keydown.enter.prevent="emit('pick', 'is')"
      @keydown.space.prevent="emit('pick', 'is')"
      >+</span
    >
    <span
      class="val-act-btn val-act-not"
      :class="{ 'val-act-on': active === 'not' }"
      role="button"
      tabindex="0"
      :aria-label="label('not')"
      :aria-pressed="active === 'not'"
      :title="label('not')"
      @click="emit('pick', 'not')"
      @keydown.enter.prevent="emit('pick', 'not')"
      @keydown.space.prevent="emit('pick', 'not')"
      >−</span
    >
  </span>
</template>
