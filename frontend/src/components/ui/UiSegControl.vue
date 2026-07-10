<script setup lang="ts" generic="T extends string">
/**
 * THE segmented bar (DESIGN.md §2: inner padding + per-option radius so the selected ring is
 * never clipped). Two tones: `accent` = coral selection language (dialog choices), `neutral` =
 * quiet card-lift selection (toolbar/menu toggles). Feedback contract lives here, once.
 */
withDefaults(
  defineProps<{
    options: readonly { value: T; label: string }[]
    modelValue: T
    tone?: 'accent' | 'neutral'
  }>(),
  { tone: 'accent' },
)
const emit = defineEmits<{ 'update:modelValue': [value: T] }>()
</script>

<template>
  <div class="ui-seg" :class="`ui-seg--${tone}`" role="group">
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
.ui-seg--accent .ui-seg-opt {
  background: var(--card);
  padding: 7px 12px;
  color: var(--ink);
}
.ui-seg--accent .ui-seg-on {
  background: var(--dd-on-bg);
  color: var(--coral-text);
  box-shadow: inset 0 0 0 1px var(--coral);
  font-weight: 600;
}
.ui-seg--neutral .ui-seg-opt {
  background: transparent;
  padding: 5px 12px;
  font-size: var(--text-control);
  font-weight: 500;
  color: var(--soft);
}
.ui-seg--neutral .ui-seg-on {
  background: var(--card);
  color: var(--ink);
  box-shadow: var(--shadow);
}
@media (prefers-reduced-motion: reduce) {
  .ui-seg-opt {
    transition: none;
  }
}
</style>
