<script setup lang="ts">
/**
 * "Data as of T; scanner silent since T′" (FR-6/D20, audit m-7) — a read-time view over
 * GET /api/v1/scanners/freshness, never written by the staleness sweep. Shown when any
 * (cluster, scanner) has been silent past the freshness window; re-checked on a 10-min poll
 * (staleness develops over days — a pinned tab must learn about it without a reload).
 * Urgency treatment (operator ruling 2026-07-10): down-ramp red, alert icon, role=alert —
 * a silent scanner is a broken pipeline, not a mild advisory.
 */
import { computed, onUnmounted, ref, watch } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import { client } from '@/api/client'
import { scannerFreshnessApiV1ScannersFreshnessGet } from '@/api/generated'
import { useClusterStore } from '@/stores/cluster'
import { useStalenessStore } from '@/stores/staleness'
import { lastDataAt, silentFor, silentRows, type FreshnessRow } from '@/system/freshness'

const POLL_MS = 10 * 60_000

const clusterStore = useClusterStore()
const staleness = useStalenessStore()
const rows = ref<FreshnessRow[]>([])

async function fetchFreshness() {
  const id = clusterStore.selectedId
  if (!id) return
  const { data, response } = await scannerFreshnessApiV1ScannersFreshnessGet({
    client,
    query: { cluster_id: id },
  })
  if (response?.ok && data) rows.value = (data as { scanners: FreshnessRow[] }).scanners ?? []
}

const timer = setInterval(() => void fetchFreshness(), POLL_MS)
onUnmounted(() => clearInterval(timer))

watch(
  () => clusterStore.selectedId,
  (id) => {
    rows.value = []
    void fetchFreshness()
    // the live window (FR-6/D20): the banner thresholds on the cluster's EFFECTIVE timers —
    // what the settings panel edits — never a build-time constant
    if (id) void staleness.loadFor(id)
  },
  { immediate: true },
)

const silent = computed(() => silentRows(rows.value, staleness.bannerThresholdS))
const clusterName = computed(() => clusterStore.selected?.cluster_name ?? clusterStore.selectedId)
</script>

<template>
  <Transition name="t-fade">
    <div v-if="silent.length" class="banner" role="alert">
      <AppIcon name="alert" :size="15" />
      <span>
        Data may be stale on <strong class="mono">{{ clusterName }}</strong> —
        <template v-for="(row, i) in silent" :key="row.scanner">
          <template v-if="i > 0"> · </template>
          <strong>{{ row.scanner }}</strong> silent {{ silentFor(row.silent_for_seconds) }}
          (last data <span class="mono">{{ lastDataAt(row.last_ingest_at) }}</span>)
        </template>
      </span>
    </div>
  </Transition>
</template>

<style scoped>
.banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: var(--health-down-bg);
  /* prose is ink — the hue lives in the wash + icon, never same-hue words on a tint */
  color: var(--ink);
  border-bottom: 1px solid var(--line);
  font-size: var(--text-body);
}
.banner svg {
  color: var(--health-down-fg);
  flex: none;
}
</style>
