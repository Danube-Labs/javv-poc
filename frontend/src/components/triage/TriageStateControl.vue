<script setup lang="ts">
/**
 * The FR-7 state grid (prototype `.state-grid`/`.state-opt` on tokens). Human targets only —
 * stale (system) and risk_accepted (decision-driven) are explained by read-only blocks in the
 * panel, never offered as buttons.
 */
import { PANEL_TARGETS } from '@/findings/triageRules'

defineProps<{ current: string; target: string | null; disabled?: boolean }>()
const emit = defineEmits<{ select: [state: string] }>()
</script>

<template>
  <div class="state-grid" role="radiogroup" aria-label="Triage state">
    <button
      v-for="t in PANEL_TARGETS"
      :key="t.state"
      type="button"
      role="radio"
      :aria-checked="(target ?? current) === t.state"
      :disabled="disabled"
      class="state-opt"
      :class="[(target ?? current) === t.state ? `state-opt-on st-${t.state}` : '']"
      @click="emit('select', t.state)"
    >
      {{ t.label }}
    </button>
  </div>
</template>

<style scoped>
.state-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.state-opt {
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: var(--r-sm);
  padding: 8px 4px;
  font-size: var(--text-control);
  font-family: var(--font-ui);
  color: var(--ink);
  font-weight: 500;
  cursor: pointer;
}
.state-opt:hover:not(:disabled) {
  border-color: var(--control-hover-line);
}
.state-opt:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.state-opt-on {
  font-weight: 600;
}
.state-opt-on.st-open {
  background: var(--state-open-bg);
  color: var(--state-open-fg);
  border-color: var(--state-open-fg);
}
.state-opt-on.st-acknowledged {
  background: var(--state-ack-bg);
  color: var(--state-ack-fg);
  border-color: var(--state-ack-fg);
}
.state-opt-on.st-resolved {
  background: var(--state-resolved-bg);
  color: var(--state-resolved-fg);
  border-color: var(--state-resolved-fg);
}
.state-opt-on.st-not_affected {
  background: var(--state-na-bg);
  color: var(--state-na-fg);
  border-color: var(--state-na-fg);
}
</style>
