<script setup lang="ts">
/** Cluster health chip (All-clusters table) — ok / stale / no data, straight from the
 * freshness rows on the D20 banner threshold. `no data` = no scanner has EVER ingested
 * (distinct from stale: seen once, silent since). */
import { computed } from 'vue'

import { freshnessStatus, type FreshnessRow } from '@/system/freshness'

const props = defineProps<{ rows: FreshnessRow[] }>()

const status = computed(() => freshnessStatus(props.rows))

const LABEL = { ok: 'healthy', stale: 'stale', none: 'no data' } as const
</script>

<template>
  <span class="health-chip" :class="`hc-${status}`">{{ LABEL[status] }}</span>
</template>

<style scoped>
.health-chip {
  font-family: var(--font-mono);
  font-size: var(--text-chip-sm);
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 2px 7px;
  border-radius: 999px;
  white-space: nowrap;
}
.hc-ok {
  color: var(--health-ok-fg);
  background: var(--health-ok-bg);
}
.hc-stale {
  color: var(--health-degraded-fg);
  background: var(--health-degraded-bg);
}
.hc-none {
  color: var(--soft);
  background: var(--panel);
  border: 1px solid var(--line2);
}
</style>
