<script setup lang="ts">
/** Labeled severity mix bar (All-clusters + Running-images tables) — proportional segments of
 * ONE scanner's severity buckets, never a cross-scanner merge (the label names whose). Zero
 * total renders the muted dash. */
import { computed } from 'vue'

import { CHART_SEV, type Severity } from '@/styles/tokens'

const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'negligible', 'unknown']

const props = defineProps<{ counts: Partial<Record<Severity, number>>; label?: string }>()

const segments = computed(() => {
  const entries = SEVERITIES.map((sev) => ({ sev, n: props.counts[sev] ?? 0 }))
  const total = entries.reduce((n, e) => n + e.n, 0)
  if (total === 0) return null
  return entries
    .filter((e) => e.n > 0)
    .map((e) => ({ sev: e.sev, pct: (e.n / total) * 100, color: CHART_SEV[e.sev] }))
})
</script>

<template>
  <div class="mix-row">
    <span v-if="label" class="mix-scanner">{{ label }}</span>
    <span v-if="segments" class="mix-bar">
      <i v-for="seg in segments" :key="seg.sev" :style="{ width: `${seg.pct}%`, background: seg.color }" />
    </span>
    <span v-else class="muted-dash">-</span>
  </div>
</template>

<style scoped>
.mix-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.mix-scanner {
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  color: var(--soft);
  width: 38px;
  flex: none;
}
.mix-bar {
  display: flex;
  flex: 1;
  min-width: 90px;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  background: var(--line2);
}
.mix-bar i {
  height: 100%;
}
.muted-dash {
  color: var(--dash-muted);
}
</style>
