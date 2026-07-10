<script setup lang="ts">
/**
 * "Data as of T; scanner silent since T′" (FR-6/D20, audit m-7) — a read-time view over
 * GET /api/v1/scanners/freshness, never written by the staleness sweep. Shown when any
 * (cluster, scanner) has been silent past the freshness window. The threshold mirrors the D20
 * default (N = 3 days); post-MVP it should read the configured `staleness` doc via the M9e
 * settings surface instead of a constant.
 */
import { computed, ref, watch } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import { client } from '@/api/client'
import { scannerFreshnessApiV1ScannersFreshnessGet } from '@/api/generated'
import { useClusterStore } from '@/stores/cluster'

const FRESHNESS_BANNER_AFTER_S = 3 * 24 * 3600

interface FreshnessRow {
  scanner: string
  last_ingest_at: string | null
  silent_for_seconds: number | null
}

const clusterStore = useClusterStore()
const rows = ref<FreshnessRow[]>([])

watch(
  () => clusterStore.selectedId,
  async (id) => {
    rows.value = []
    if (!id) return
    const { data, response } = await scannerFreshnessApiV1ScannersFreshnessGet({
      client,
      query: { cluster_id: id },
    })
    if (response?.ok && data) rows.value = (data as { scanners: FreshnessRow[] }).scanners ?? []
  },
  { immediate: true },
)

const silent = computed(() =>
  rows.value.filter((r) => (r.silent_for_seconds ?? 0) > FRESHNESS_BANNER_AFTER_S),
)

function since(row: FreshnessRow): string {
  return row.last_ingest_at ? new Date(row.last_ingest_at).toLocaleString() : 'never'
}
</script>

<template>
  <Transition name="t-fade">
    <div v-if="silent.length" class="banner" role="status">
      <AppIcon name="clock" :size="15" />
      <span>
        Data may be stale —
        <template v-for="(row, i) in silent" :key="row.scanner">
          <template v-if="i > 0"> · </template>
          <strong>{{ row.scanner }}</strong> silent since
          <span class="mono">{{ since(row) }}</span>
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
  background: var(--health-degraded-bg);
  color: var(--ink);
  border-bottom: 1px solid var(--line);
  font-size: var(--text-body);
}
</style>
