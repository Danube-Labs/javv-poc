<script setup lang="ts">
/**
 * SLA-hit percentage pill (M9d slice 3; prototype `.sla-pct`, tiers pinned in viewModel).
 * Wears the state-tone families (good=resolved, ok=ack, low=open) — a quiet tonal badge,
 * never an alarm chip; null (no SLA-bearing sample) renders the honest dash.
 */
import { computed } from 'vue'

import { slaTier } from '@/contributors/viewModel'

const props = defineProps<{ pct: number | null }>()
const tier = computed(() => slaTier(props.pct))
</script>

<template>
  <span v-if="tier" class="sla-pct" :data-tier="tier">{{ Math.round(pct!) }}%</span>
  <span v-else class="sla-none mono-cell sm">—</span>
</template>

<style scoped>
.sla-pct {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  padding: 2px 7px;
  border-radius: var(--r-sm);
}
.sla-pct[data-tier='good'] {
  color: var(--state-resolved-fg);
  background: var(--state-resolved-bg);
}
.sla-pct[data-tier='ok'] {
  color: var(--state-ack-fg);
  background: var(--state-ack-bg);
}
.sla-pct[data-tier='low'] {
  color: var(--state-open-fg);
  background: var(--state-open-bg);
}
.sla-none {
  color: var(--muted);
}
</style>
