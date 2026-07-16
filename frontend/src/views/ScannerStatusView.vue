<script setup lang="ts">
/**
 * Scanner status screen (M9d slice 2; SCREENS §12, C-3 redesign): the shared data-screen
 * band (head-card + the scan-ingest lens — the same "committed runs per bucket, per scanner"
 * strip findings/images carry, operator ruling 2026-07-12) over per-(cluster, scanner) cards
 * — D20 freshness + D41 read-only provenance + last-N committed runs. The prototype's
 * failed-ingests feed is CUT by ruling (A-7/D-4): dead-lettering is scanner-local by design,
 * so no feed exists to show. Freshness/provenance are NOW-truth reads — at a rewound T the
 * screen renders the C-1/D39 limitation notice instead of data.
 */
import { computed, ref, watch } from 'vue'

import {
  scannerFreshnessApiV1ScannersFreshnessGet,
  scannerProvenanceApiV1ScannersProvenanceGet,
} from '@/api/generated'
import { client } from '@/api/client'
import IngestLens from '@/components/dashboards/IngestLens.vue'
import LimitedHistoricalNotice from '@/components/dashboards/LimitedHistoricalNotice.vue'
import ScannerRunsTable from '@/components/scanners/ScannerRunsTable.vue'
import ScannerStatusCard, {
  type ProvenanceRow,
} from '@/components/scanners/ScannerStatusCard.vue'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import type { FreshnessRow } from '@/system/freshness'

const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()

const RUNS_FETCHED = 50 // the provenance endpoint's own last-N cap; GridPager slices it

const freshness = ref<FreshnessRow[]>([])
const provenance = ref<ProvenanceRow[]>([])
const loading = ref(true)
const failed = ref(false)

watch(
  () => [clusterStore.selectedId, timeTravel.t] as const,
  async ([id, t]) => {
    if (!id || t !== null) return // T<now renders the limitation notice, no reads (C-1/D39)
    loading.value = true
    const [fresh, prov] = await Promise.all([
      scannerFreshnessApiV1ScannersFreshnessGet({ client, query: { cluster_id: id } }),
      scannerProvenanceApiV1ScannersProvenanceGet({
        client,
        query: { cluster_id: id, runs: RUNS_FETCHED } as never,
      }),
    ])
    loading.value = false
    failed.value = !fresh.response?.ok || !prov.response?.ok
    if (failed.value) {
      logger.warn('scanner_status_failed', {
        freshness: fresh.response?.status,
        provenance: prov.response?.status,
      })
      return
    }
    freshness.value = (fresh.data as { scanners: FreshnessRow[] }).scanners ?? []
    provenance.value = (prov.data as { scanners: ProvenanceRow[] }).scanners ?? []
  },
  { immediate: true },
)

/** one card per scanner either read knows about — a scanner with freshness but no committed
 * run still shows (its card says so) */
const scanners = computed(() => {
  const names = new Set<string>([
    ...provenance.value.map((p) => p.scanner),
    ...freshness.value.map((f) => f.scanner),
  ])
  return [...names].sort().map((name) => ({
    name,
    provenance: provenance.value.find((p) => p.scanner === name) ?? null,
    freshness: freshness.value.find((f) => f.scanner === name) ?? null,
  }))
})
</script>

<template>
  <div class="screen">
    <div class="screen-head screen-head-band">
      <div class="head-card">
        <h1>Scanner status</h1>
        <p class="head-stat">
          {{ scanners.length }}<span class="head-unit"> scanners</span>
        </p>
        <p class="head-note">committed runs only · versions are read-only provenance</p>
      </div>
      <IngestLens
        v-if="clusterStore.selectedId"
        :cluster-id="clusterStore.selectedId"
        subject="this screen"
      />
    </div>

    <LimitedHistoricalNotice
      v-if="timeTravel.t !== null"
      title="Historical scanner status is limited until the v1.1 metrics rollup"
      body="Freshness and provenance answer for now — the committed-run history you can rewind
        lives in the ingest lens above. Return to now for live scanner health."
    />

    <template v-else>
      <div v-if="loading" class="scan-cards" aria-busy="true" aria-label="Loading scanner status">
        <div class="skel skel-card" />
        <div class="skel skel-card" />
      </div>

      <p v-else-if="failed" class="load-error" role="alert">
        Scanner status unavailable. Check the backend connection.
      </p>

      <div v-else-if="scanners.length === 0" class="not-found" role="status">
        <p>No scanner has reported for this cluster yet — the first committed run lands here.</p>
      </div>

      <div v-else class="scan-cards">
        <div v-for="s in scanners" :key="s.name" class="scan-stack">
          <ScannerStatusCard
            :scanner="s.name"
            :provenance="s.provenance"
            :freshness="s.freshness"
          />
          <!-- the committed-run timeline: shared table template + shared pager -->
          <ScannerRunsTable
            v-if="(s.provenance?.runs ?? []).length"
            :runs="s.provenance!.runs!"
            :scanner="s.name"
            :cap="RUNS_FETCHED"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* prototype .scan-cards grid; band/head scaffolding lives in base.css */
.scan-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  align-items: start;
}
.scan-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
@media (width <= 1100px) {
  .scan-cards {
    grid-template-columns: 1fr;
  }
}
.load-error {
  margin: 0;
}
.not-found {
  padding: var(--space-8) 0;
  text-align: center;
  color: var(--soft);
}
.skel {
  border-radius: var(--r);
  background: linear-gradient(90deg, var(--line2) 25%, var(--panel) 50%, var(--line2) 75%);
  background-size: 200% 100%;
  animation: skel-shimmer 1.4s ease-in-out infinite;
}
.skel-card {
  height: 300px;
}
@keyframes skel-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .skel {
    animation: none;
  }
}
</style>
