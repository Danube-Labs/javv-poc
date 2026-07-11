<script setup lang="ts">
/**
 * THE button. Every variant carries the full interaction contract (DESIGN.md §2:
 * hover wash + border shift, pressed, focus ring, arrow cursor, disabled) internally,
 * so consumers can't ship a button that skips it.
 */
withDefaults(
  defineProps<{
    variant?: 'mini' | 'control' | 'quiet' | 'ghost' | 'primary'
    block?: boolean
  }>(),
  { variant: 'mini' },
)
</script>

<template>
  <button type="button" class="ui-btn" :class="[`ui-btn--${variant}`, { 'ui-btn--block': block }]">
    <slot />
  </button>
</template>

<style scoped>
.ui-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: var(--r-sm);
  font-family: var(--font-ui);
  color: var(--ink);
  cursor: default;
  transition:
    background 120ms ease,
    border-color 120ms ease;
}
.ui-btn:hover:not(:disabled) {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.ui-btn:active:not(:disabled) {
  background: var(--control-active-bg);
}
.ui-btn:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.ui-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.ui-btn--mini {
  padding: 4px 9px;
  font-size: var(--text-sm);
}
.ui-btn--control {
  padding: 6px 11px;
  font-size: var(--text-control);
}
.ui-btn--quiet {
  gap: 7px;
  padding: 5px 9px;
  font-size: var(--text-quiet-action);
  font-weight: 600;
  background: var(--panel);
  border-radius: 7px;
}
.ui-btn--ghost,
.ui-btn--primary {
  gap: 7px;
  padding: 8px 14px;
  font-size: var(--text-control);
  font-weight: 600;
}
.ui-btn--primary {
  border-color: var(--coral-d);
  background: var(--coral);
  color: var(--kev-fg);
  /* chip-language-A depth: inner highlight + soft brand drop; pressed goes flat */
  box-shadow: inset 0 1px 0 var(--chip-hi), 0 1px 2px var(--coral-drop);
}
.ui-btn--primary:hover:not(:disabled) {
  background: var(--coral-d);
  border-color: var(--coral-d);
}
.ui-btn--primary:active:not(:disabled) {
  background: var(--coral-d);
  box-shadow: none;
}
.ui-btn--block {
  width: 100%;
}
@media (prefers-reduced-motion: reduce) {
  .ui-btn {
    transition: none;
  }
}
</style>
