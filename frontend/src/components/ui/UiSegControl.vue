<script setup lang="ts" generic="T extends string">
/**
 * THE segmented bar (DESIGN.md §2: inner padding + per-option radius so the selected ring is
 * never clipped). ONE selection language — the coral tint (operator ruling 2026-07-11: the old
 * `neutral` tone's white-on-panel selection was unreadable; every seg control selects loudly).
 * Feedback contract lives here, once.
 */
withDefaults(
  defineProps<{
    options: readonly { value: T; label: string }[]
    modelValue: T
  }>(),
  {},
)
const emit = defineEmits<{ 'update:modelValue': [value: T] }>()
</script>

<template>
  <div class="ui-seg" role="group">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="ui-seg-opt"
      :class="{ 'ui-seg-on': modelValue === opt.value }"
      :aria-pressed="modelValue === opt.value"
      @click="emit('update:modelValue', opt.value)"
    >
      {{ opt.label }}
    </button>
  </div>
</template>

<style scoped>
.ui-seg {
  display: inline-flex;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--panel);
}
.ui-seg-opt {
  border: 0;
  border-radius: 5px;
  font-family: var(--font-ui);
  font-size: var(--text-sm);
  white-space: nowrap;
  cursor: default;
  background: var(--card);
  padding: 7px 12px;
  color: var(--ink);
  transition:
    background 120ms ease,
    color 120ms ease;
}
.ui-seg-opt:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.ui-seg-opt:hover:not(.ui-seg-on) {
  background: var(--control-hover-bg);
  color: var(--ink);
}
.ui-seg-opt:active:not(.ui-seg-on) {
  background: var(--control-active-bg);
}
.ui-seg-on {
  background: var(--dd-on-bg);
  color: var(--coral-text);
  box-shadow: inset 0 0 0 1px var(--coral);
  font-weight: 600;
}
@media (prefers-reduced-motion: reduce) {
  .ui-seg-opt {
    transition: none;
  }
}
</style>
