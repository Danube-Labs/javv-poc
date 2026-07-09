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
  <span class="state-tag" :data-state="state in LABELS ? state : 'open'">{{ label }}</span>
</template>

<style scoped>
.state-tag {
  font-size: var(--text-chip);
  font-weight: 600;
  padding: 3px 9px;
  border-radius: 20px;
  border: 1px solid transparent;
  white-space: nowrap;
}
.state-tag[data-state='open'] { background: var(--state-open-bg); color: var(--state-open-fg); border-color: var(--state-open-line); }
.state-tag[data-state='stale'] { background: var(--state-stale-bg); color: var(--state-stale-fg); border-color: var(--state-stale-line); }
.state-tag[data-state='acknowledged'] { background: var(--state-ack-bg); color: var(--state-ack-fg); border-color: var(--state-ack-line); }
.state-tag[data-state='not_affected'] { background: var(--state-na-bg); color: var(--state-na-fg); border-color: var(--state-na-line); }
.state-tag[data-state='risk_accepted'] { background: var(--state-risk-bg); color: var(--state-risk-fg); border-color: var(--state-risk-line); }
.state-tag[data-state='resolved'] { background: var(--state-resolved-bg); color: var(--state-resolved-fg); border-color: var(--state-resolved-line); }
</style>
