<script setup lang="ts">
/**
 * The ingest lens — a Kibana-Discover-style strip above a data table: committed scan runs
 * per day over the global time range, per scanner (never merged), plus WHEN data last
 * arrived. It exists to answer "why does the table still show findings when the scanners
 * are idle?" — the table shows state at the END of the range (D28); this strip shows the
 * ingest moments inside it. Drop it above any cluster-scoped table.
 *
 * Every number is a server aggregation: `GET /trends/scans` (cardinality-deduped committed
 * runs) + `GET /scanners/freshness`. The freshness line is NOW-truth, so it hides at a
 * past T — there the range copy alone carries the message.
 */
import { computed, ref, watch } from 'vue'

import { client } from '@/api/client'
import {
  scannerFreshnessApiV1ScannersFreshnessGet,
  scansTrendApiV1TrendsScansGet,
} from '@/api/generated'
import { buildIngestLensOption } from '@/charts/buildIngestLensOption'
import type { ScanActivityData } from '@/charts/buildScanActivityOption'
import { buildTrendQuery } from '@/charts/buildTrendQuery'
import EChart from '@/components/charts/EChart.vue'
import { logger } from '@/lib/logger'
import { lastDataAt, silentFor, type FreshnessRow } from '@/system/freshness'
import { useTimeTravelStore } from '@/stores/timeTravel'

const props = defineProps<{ clusterId: string }>()
const timeTravel = useTimeTravelStore()

const series = ref<ScanActivityData>({})
const freshness = ref<FreshnessRow[]>([])
const failed = ref(false)

watch(
  () => [props.clusterId, timeTravel.t, timeTravel.windowDays] as const,
  async ([id, t, days]) => {
    if (!id) return
    const [scans, fresh] = await Promise.all([
      scansTrendApiV1TrendsScansGet({
        client,
        query: buildTrendQuery(id, days, t) as never,
      }),
      scannerFreshnessApiV1ScannersFreshnessGet({ client, query: { cluster_id: id } }),
    ])
    failed.value = !scans.response?.ok
    if (failed.value) logger.warn('ingest_lens_failed', { status: scans.response?.status })
    series.value = scans.response?.ok
      ? ((scans.data as { series: ScanActivityData }).series ?? {})
      : {}
    if (fresh.response?.ok && fresh.data) {
      freshness.value = (fresh.data as { scanners: FreshnessRow[] }).scanners ?? []
    }
  },
  { immediate: true },
)

const totalRuns = computed(() =>
  Object.values(series.value).reduce(
    (n, rows) => n + (rows ?? []).reduce((m, p) => m + p.scans, 0),
    0,
  ),
)
const latest = computed(
  () =>
    freshness.value
      .filter((r) => r.last_ingest_at !== null)
      .sort((a, b) => (a.last_ingest_at! < b.last_ingest_at! ? 1 : -1))[0] ?? null,
)
const option = computed(() => buildIngestLensOption(series.value))
</script>

<template>
  <section class="ingest-lens" aria-label="Scan ingest activity">
    <div class="il-head">
      <h3 class="il-title">Scan ingest</h3>
      <span class="il-sub">committed runs per day · {{ timeTravel.windowLabel.toLowerCase() }}</span>
      <span v-if="timeTravel.isNow && latest" class="il-last mono-cell">
        last ingest {{ latest.scanner }} · {{ lastDataAt(latest.last_ingest_at) }} ({{
          silentFor(latest.silent_for_seconds)
        }} ago)
      </span>
    </div>
    <p v-if="failed" class="il-empty">Ingest activity unavailable.</p>
    <p v-else-if="totalRuns === 0" class="il-empty">
      No scans committed in this range<template v-if="timeTravel.isNow && latest">
        — the table below shows the state last updated {{ lastDataAt(latest.last_ingest_at) }},
        {{ silentFor(latest.silent_for_seconds) }} ago</template
      >.
    </p>
    <EChart v-else :option="option" :height="72" />
  </section>
</template>

<style scoped>
.ingest-lens {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 10px 14px 6px;
  margin-bottom: 12px;
}
.il-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
}
.il-title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink);
}
.il-sub {
  font-size: var(--text-sm);
  color: var(--soft);
}
.il-last {
  margin-left: auto;
  font-size: var(--text-sm);
  color: var(--soft);
}
.il-empty {
  margin: 2px 0 8px;
  font-size: var(--text-body);
  color: var(--soft);
}
</style>
