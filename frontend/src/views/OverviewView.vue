<script setup lang="ts">
/**
 * Overview — single-cluster dashboard (M9c slice 1; SCREENS §2, prototype screens-overview.jsx
 * ported structure-only onto tokens). KPI strip is the joined hairline-divided stat band (Nuxt UI
 * stat grammar — operator ruling from the finding-detail risk band) with click-through cells.
 * Every number is a server aggregation; the scanner seg only re-reads the by_scanner splits the
 * server already returned. Cut vs prototype (recorded in the bolt README): KPI sparklines +
 * "+new 30d" chips (no per-severity trend agg), namespace severity MixBar (no per-ns severity
 * agg), Top components / Language binaries / Newly published (B-6/B-2).
 * Issue-384 split: the stat bands and the namespaces card live in components/overview/;
 * the scanner-lens count math is the shared pure helper views/overviewLens.ts.
 */
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'

import { buildFindingsTrendOption } from '@/charts/buildFindingsTrendOption'
import { buildPtypeDonutOption } from '@/charts/buildPtypeDonutOption'
import { buildScanActivityOption } from '@/charts/buildScanActivityOption'
import { buildSeverityTrendOption, type SeverityTrendData } from '@/charts/buildSeverityTrendOption'
import { isSubDayWindow } from '@/charts/buildTrendQuery'
import EChart from '@/components/charts/EChart.vue'
import IngestLens from '@/components/dashboards/IngestLens.vue'
import OverviewNamespacesCard from '@/components/overview/OverviewNamespacesCard.vue'
import OverviewStatBands from '@/components/overview/OverviewStatBands.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { useApi } from '@/composables/useApi'
import { CHART_PTYPE_RAMP } from '@/styles/tokens'
import { useClusterStore } from '@/stores/cluster'
import { useOverviewStore } from '@/stores/overview'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { countOf, fmt, type ScannerLens } from '@/views/overviewLens'
import { ref } from 'vue'

const SCANNER_OPTS = [
  { value: 'all', label: 'All scanners' },
  { value: 'trivy', label: 'trivy' },
  { value: 'grype', label: 'grype' },
] as const

const router = useRouter()
const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const overview = useOverviewStore()
const { withGlobals } = useApi()

const scanner = ref<ScannerLens>('all')
const LENS_OPTS = [
  { value: 'scanner', label: 'by scanner' },
  { value: 'severity', label: 'by severity' },
] as const
const trendLens = ref<'scanner' | 'severity'>('scanner')

watch(
  () => [clusterStore.selectedId, timeTravel.t, timeTravel.windowDays] as const,
  ([id, t]) => {
    if (!id) return
    void overview.load(withGlobals({ cluster_id: id }), timeTravel.windowDays)
    if (t !== null) trendLens.value = 'scanner' // severity lens is a now-only read (route 422s)
  },
  { immediate: true },
)
watch(
  [trendLens, scanner, () => clusterStore.selectedId, () => timeTravel.windowDays],
  ([lens, sc, id]) => {
    if (lens === 'severity' && id && timeTravel.isNow) {
      void overview.loadSeverityTrend(id, timeTravel.windowDays, sc === 'all' ? null : sc)
    }
  },
)

const trendOption = computed(() => {
  if (trendLens.value === 'severity') {
    return buildSeverityTrendOption(overview.sevTrend as SeverityTrendData)
  }
  if (scanner.value === 'all') return buildFindingsTrendOption(overview.trend)
  return buildFindingsTrendOption({
    new: { [scanner.value]: overview.trend.new[scanner.value] },
    resolved: { [scanner.value]: overview.trend.resolved[scanner.value] },
  })
})

const scansOption = computed(() =>
  buildScanActivityOption(
    scanner.value === 'all'
      ? overview.scans
      : { [scanner.value]: overview.scans[scanner.value] },
  ),
)

/** ptype buckets minus a lone `unknown` (pre-M8d rows heal on the next sweep, D30). */
const ptypeBuckets = computed(() => {
  const all = (overview.facets.ptype ?? []).map((b) => ({
    key: b.key,
    count: countOf(b, scanner.value),
  }))
  const real = all.filter((b) => b.key !== 'unknown' && b.count > 0)
  return real
})
const donutOption = computed(() => buildPtypeDonutOption(ptypeBuckets.value))

const lastSweep = computed(() => {
  if (!overview.lastIngestAt) return null
  return new Date(overview.lastIngestAt).toLocaleString('en-GB', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
})

const subDayNote = computed(() => isSubDayWindow(timeTravel.windowDays))

function goFindings(query: Record<string, string>) {
  void router.push({ path: '/findings', query })
}
function onDonutClick(e: { name?: string }) {
  if (e?.name) goFindings({ ptype: e.name })
}
</script>

<template>
  <div class="screen">
    <div class="screen-head">
      <div class="head-card head-card-fluid">
        <h1>Overview</h1>
        <p class="head-note">
          Current state across <b class="mono-cell">{{ clusterStore.selected?.cluster_name ?? '—' }}</b>
          <template v-if="lastSweep"> · last sweep <span class="mono-cell">{{ lastSweep }}</span></template>
        </p>
      </div>
      <div class="head-actions">
        <UiSegControl v-model="scanner" :options="SCANNER_OPTS" />
        <UiButton variant="primary" @click="goFindings({ severity: 'critical' })">
          Triage critical <AppIcon name="chevron" :size="13" />
        </UiButton>
      </div>
    </div>

    <IngestLens
      v-if="clusterStore.selectedId"
      class="ov-lens"
      :cluster-id="clusterStore.selectedId"
      subject="this screen"
    />

    <div v-if="overview.loading" aria-busy="true" aria-label="Loading overview">
      <div class="skel skel-band" />
      <div class="skel skel-card" />
    </div>

    <p v-else-if="overview.failed" class="load-error" role="alert">
      Overview unavailable. Check the backend connection.
    </p>

    <div v-else-if="overview.empty" class="first-run">
      <h2>No sweep has landed yet</h2>
      <p>
        KPIs and trends appear after the first scanner cycle commits. Scanner status shows
        per-scanner progress.
      </p>
    </div>

    <template v-else>
      <OverviewStatBands :scanner="scanner" />

      <div class="grid grid-2-1">
        <section class="card">
          <div class="card-head">
            <div>
              <h3>Vulnerabilities over time</h3>
              <p class="card-sub">
                new per day · {{ timeTravel.windowLabel.toLowerCase() }}<template
                  v-if="trendLens === 'scanner'"
                > · resolved = scan-observed</template>
              </p>
            </div>
            <UiSegControl
              v-if="timeTravel.isNow"
              v-model="trendLens"

              :options="LENS_OPTS"
            />
          </div>
          <div class="card-body">
            <EChart :option="trendOption" :height="250" />
            <p v-if="subDayNote" class="chart-note">
              Trend at daily resolution — chart covers the last 1 day.
            </p>
          </div>
        </section>
        <section class="card">
          <div class="card-head">
            <div>
              <h3>Package type</h3>
              <p class="card-sub">share of findings</p>
            </div>
          </div>
          <div class="card-body">
            <template v-if="ptypeBuckets.length">
              <EChart :option="donutOption" :height="188" @click="onDonutClick" />
              <div class="donut-legend">
                <button
                  v-for="(b, i) in ptypeBuckets.slice(0, 6)"
                  :key="b.key"
                  class="donut-row"
                  :title="`Open ${b.key} findings`"
                  @click="goFindings({ ptype: b.key })"
                >
                  <i :style="{ background: CHART_PTYPE_RAMP[i % CHART_PTYPE_RAMP.length] }" />
                  {{ b.key }}<AppIcon class="cell-go" name="chevron" :size="11" /> <b>{{ fmt(b.count) }}</b>
                </button>
              </div>
            </template>
            <p v-else class="empty-row">
              Awaiting package-type data — populates as the next scan cycles re-observe images.
            </p>
          </div>
        </section>
      </div>

      <div class="grid grid-1-1">
        <section class="card">
          <div class="card-head">
            <div>
              <h3>Scan activity</h3>
              <p class="card-sub">committed runs per day, per scanner</p>
            </div>
          </div>
          <div class="card-body">
            <EChart :option="scansOption" :height="190" />
            <p v-if="subDayNote" class="chart-note">
              Trend at daily resolution — chart covers the last 1 day.
            </p>
          </div>
        </section>
        <OverviewNamespacesCard :scanner="scanner" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.ov-lens {
  margin-bottom: 16px;
}
.screen-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.grid {
  display: grid;
  gap: var(--grid-gap);
  margin-top: 16px;
}
.grid-2-1 {
  grid-template-columns: 1.55fr 1fr;
}
.grid-1-1 {
  grid-template-columns: 1fr 1fr;
}
@media (max-width: 1120px) {
  .grid-2-1,
  .grid-1-1 {
    grid-template-columns: 1fr;
  }
}

.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
}
.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px 0;
}
.card-head h3 {
  margin: 0;
}
.card-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.card-body {
  padding: 10px 16px 14px;
}
.chart-note {
  margin: 6px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}

.donut-legend {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}
.donut-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-sweep-strong);
  color: var(--soft);
  border: none;
  background: none;
  padding: 2px 4px;
  border-radius: 5px;
  cursor: default;
  text-align: left;
  transition: background var(--dur-quick);
}
.donut-row:hover {
  background: var(--control-hover-bg);
  color: var(--ink);
}
.donut-row:active {
  background: var(--control-active-bg);
}
.donut-row:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.donut-row:hover .cell-go {
  color: var(--coral-text);
}
.donut-row i {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  flex: none;
}
.donut-row b {
  margin-left: auto;
  color: var(--ink);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

.load-error {
  color: var(--health-down-fg);
  font-size: var(--text-body);
}
.first-run {
  padding: 48px 0;
  text-align: center;
  color: var(--soft);
}
.first-run h2 {
  color: var(--ink);
  margin: 0 0 6px;
}

/* skeletons (product register: skeletons over spinners) */
.skel {
  border-radius: var(--r);
  background: linear-gradient(90deg, var(--line2) 25%, var(--panel) 50%, var(--line2) 75%);
  background-size: 200% 100%;
  animation: skel-shimmer 1.4s ease-in-out infinite;
}
.skel-band {
  height: 96px;
}
.skel-card {
  height: 300px;
  margin-top: 16px;
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
