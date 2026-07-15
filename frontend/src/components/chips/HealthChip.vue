<script setup lang="ts">
/** Cluster health chip (All-clusters table) — ok / stale / no data, straight from the
 * freshness rows on the D20 banner threshold. `no data` = no scanner has EVER ingested
 * (distinct from stale: seen once, silent since). */
import { computed } from 'vue'

import { freshnessStatus, type FreshnessRow } from '@/system/freshness'

const props = defineProps<{ rows: FreshnessRow[]; thresholdS?: number }>()

const status = computed(() => freshnessStatus(props.rows, props.thresholdS))

const LABEL = { ok: 'healthy', stale: 'stale', none: 'no data' } as const
</script>

<template>
  <span class="health-chip" :class="`hc-${status}`"><i class="hc-dot" aria-hidden="true" />{{ LABEL[status] }}</span>
</template>

<style scoped>
/* language A: status dot + plain word — the sidebar sweep-dot grammar, reused; the halo
   ring (the family tint) is the depth accent */
.health-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
}
.hc-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
}
.hc-ok .hc-dot {
  background: var(--health-ok-dot);
  box-shadow: 0 0 0 3px var(--health-ok-bg);
}
.hc-stale .hc-dot {
  background: var(--health-degraded-dot);
  box-shadow: 0 0 0 3px var(--health-degraded-bg);
}
.hc-none {
  color: var(--soft);
}
.hc-none .hc-dot {
  background: var(--health-none-dot);
}
</style>
