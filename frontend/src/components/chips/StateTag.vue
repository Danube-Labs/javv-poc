<script setup lang="ts">
/**
 * Finding-state pill (prototype `StateTag` + `.state-tag`/`.st-*` CSS) — all SIX states of the
 * shipped model (A-2): open · acknowledged · not_affected · risk_accepted · resolved · stale.
 */
import { computed } from 'vue'

const LABELS: Record<string, string> = {
  open: 'Open',
  stale: 'Stale',
  acknowledged: 'Acknowledged',
  not_affected: 'Not affected',
  risk_accepted: 'Risk accepted',
  resolved: 'Resolved',
}

const props = defineProps<{ state: string }>()
// computed, not a setup-time const — the state prop changes in place after a triage save
const label = computed(() => LABELS[props.state] ?? props.state)
</script>

<template>
  <span class="state-tag" :data-state="state in LABELS ? state : 'open'">
    <i class="st-dot" aria-hidden="true" />{{ label }}
  </span>
</template>

<style scoped>
/* Chip language A (operator 2026-07-11): workflow reads QUIETER than severity — soft
   derived tint + a solid lifecycle dot, sentence case, no ring. */
.state-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-sm);
  font-weight: 500;
  padding: 3px 10px;
  border-radius: 999px;
  white-space: nowrap;
}
.st-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
}
.state-tag[data-state='open'] { background: var(--state-open-bg); color: var(--state-open-fg); }
.state-tag[data-state='open'] .st-dot { background: var(--state-open-solid); }
.state-tag[data-state='stale'] { background: var(--state-stale-bg); color: var(--state-stale-fg); }
.state-tag[data-state='stale'] .st-dot { background: var(--state-stale-solid); }
.state-tag[data-state='acknowledged'] { background: var(--state-ack-bg); color: var(--state-ack-fg); }
.state-tag[data-state='acknowledged'] .st-dot { background: var(--state-ack-solid); }
.state-tag[data-state='not_affected'] { background: var(--state-na-bg); color: var(--state-na-fg); }
.state-tag[data-state='not_affected'] .st-dot { background: var(--state-na-solid); }
.state-tag[data-state='risk_accepted'] { background: var(--state-risk-bg); color: var(--state-risk-fg); }
.state-tag[data-state='risk_accepted'] .st-dot { background: var(--state-risk-solid); }
.state-tag[data-state='resolved'] { background: var(--state-resolved-bg); color: var(--state-resolved-fg); }
.state-tag[data-state='resolved'] .st-dot { background: var(--state-resolved-solid); }
</style>
