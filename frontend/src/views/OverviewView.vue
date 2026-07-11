<script setup lang="ts">
/**
 * Overview — single-cluster dashboard (M9c slice 1; SCREENS-v5 §2, prototype screens-overview.jsx
 * ported structure-only onto tokens). KPI strip is the joined hairline-divided stat band (Nuxt UI
 * stat grammar — operator ruling from the finding-detail risk band) with click-through cells.
 * Every number is a server aggregation; the scanner seg only re-reads the by_scanner splits the
 * server already returned. Cut vs prototype (recorded in the bolt README): KPI sparklines +
 * "+new 30d" chips (no per-severity trend agg), namespace severity MixBar (no per-ns severity
 * agg), Top components / Language binaries / Newly published (B-6/B-2).
 */
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'

import { buildFindingsTrendOption } from '@/charts/buildFindingsTrendOption'
import { buildPtypeDonutOption } from '@/charts/buildPtypeDonutOption'
import { buildScanActivityOption } from '@/charts/buildScanActivityOption'
import { buildSeverityTrendOption, type SeverityTrendData } from '@/charts/buildSeverityTrendOption'
import { isSubDayWindow } from '@/charts/buildTrendQuery'
import EChart from '@/components/charts/EChart.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { useApi } from '@/composables/useApi'
import { CHART_PTYPE_RAMP, CHART_SEV, type Severity } from '@/styles/tokens'
import { useClusterStore } from '@/stores/cluster'
import { useOverviewStore, type FacetBucket } from '@/stores/overview'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { ref } from 'vue'

const KPI_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low']
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

const scanner = ref<'all' | 'trivy' | 'grype'>('all')
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

/** A bucket's display count under the scanner lens — the server's by_scanner split, never a
 * client re-aggregation. */
function countOf(bucket: FacetBucket | null): number {
  if (!bucket) return 0
  return scanner.value === 'all' ? bucket.count : (bucket.by_scanner[scanner.value] ?? 0)
}
const sevCount = (s: Severity) => countOf(overview.bucket('severity', s))
const totalPresent = computed(() => countOf(overview.bucket('present', 'true')))
const fixableCount = computed(() => countOf(overview.bucket('fixable', 'true')))
const fixPct = computed(() =>
  totalPresent.value === 0 ? 0 : Math.round((fixableCount.value / totalPresent.value) * 100),
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

/* 1b quick views — all straight facet reads */
const kevCount = computed(() => countOf(overview.bucket('kev', 'true')))
const disagreeCount = computed(() => countOf(overview.bucket('disagree', 'true')))
const stateCount = (k: string) => countOf(overview.bucket('state', k))
const handledCount = computed(
  () => stateCount('resolved') + stateCount('not_affected') + stateCount('risk_accepted'),
)
const triage = computed(() => {
  const open = stateCount('open')
  const ack = stateCount('acknowledged')
  const stale = stateCount('stale')
  const handled = handledCount.value
  const total = open + ack + stale + handled
  const pct = (n: number) => (total === 0 ? 0 : (n / total) * 100)
  return { open, ack, stale, handled, total, pct }
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
  const all = (overview.facets.ptype ?? []).map((b) => ({ key: b.key, count: countOf(b) }))
  const real = all.filter((b) => b.key !== 'unknown' && b.count > 0)
  return real
})
const donutOption = computed(() => buildPtypeDonutOption(ptypeBuckets.value))

const namespaces = computed(() =>
  (overview.facets.namespaces ?? [])
    .map((b) => ({ key: b.key, count: countOf(b) }))
    .filter((b) => b.count > 0)
    .slice(0, 10),
)

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
const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <div class="screen">
    <div class="screen-head">
      <div>
        <h1>Overview</h1>
        <p class="screen-sub">
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
      <!-- KPI band: joined, hairline-divided (Nuxt stat grammar on our tokens) -->
      <div class="kpi-band">
        <button
          v-for="s in KPI_SEVERITIES"
          :key="s"
          class="kpi-cell"
          :title="`Open findings filtered to ${s}`"
          @click="goFindings({ severity: s })"
        >
          <span class="kpi-label"><i class="kpi-dot" :style="{ background: CHART_SEV[s] }" />{{ s }}<AppIcon class="cell-go" name="chevron" :size="11" /></span>
          <span class="kpi-num">{{ fmt(sevCount(s)) }}</span>
        </button>
        <button class="kpi-cell" title="Open findings with a fix available" @click="goFindings({ attr: 'fixable' })">
          <span class="kpi-label"><i class="kpi-dot kpi-dot-fix" />fix available<AppIcon class="cell-go" name="chevron" :size="11" /></span>
          <span class="kpi-num">{{ fixPct }}%</span>
          <span class="kpi-sub">{{ fmt(fixableCount) }} findings patchable today</span>
        </button>
      </div>

      <!-- signal band (1b): urgency + quality quick views, same joined grammar -->
      <div class="kpi-band signal-band">
        <button class="kpi-cell" title="Open known-exploited findings" @click="goFindings({ attr: 'kev' })">
          <span class="kpi-label"><i class="kpi-dot kpi-dot-kev" />KEV · known-exploited<AppIcon class="cell-go" name="chevron" :size="11" /></span>
          <span class="kpi-num" :class="{ 'kpi-num-alarm': kevCount > 0 }">{{ fmt(kevCount) }}</span>
        </button>
        <button class="kpi-cell" title="Open findings where the scanners disagree" @click="goFindings({ attr: 'disagree' })">
          <span class="kpi-label"><i class="kpi-dot kpi-dot-disagree" />scanners disagree<AppIcon class="cell-go" name="chevron" :size="11" /></span>
          <span class="kpi-num">{{ fmt(disagreeCount) }}</span>
        </button>
        <button class="kpi-cell" title="Open the untriaged queue" @click="goFindings({ state: 'open' })">
          <span class="kpi-label"><i class="kpi-dot kpi-dot-progress" />triage progress<AppIcon class="cell-go" name="chevron" :size="11" /></span>
          <span class="kpi-num">{{ triage.total === 0 ? '—' : `${Math.round(triage.pct(triage.handled + triage.ack))}%` }}</span>
          <span class="progress-bar" aria-hidden="true">
            <i class="seg-open" :style="{ width: `${triage.pct(triage.open)}%` }" />
            <i class="seg-ack" :style="{ width: `${triage.pct(triage.ack)}%` }" />
            <i class="seg-handled" :style="{ width: `${triage.pct(triage.handled)}%` }" />
            <i class="seg-stale" :style="{ width: `${triage.pct(triage.stale)}%` }" />
          </span>
          <span class="kpi-sub">{{ fmt(triage.open) }} open · {{ fmt(triage.ack) }} ack · {{ fmt(triage.handled) }} handled<template v-if="triage.stale"> · {{ fmt(triage.stale) }} stale</template></span>
        </button>
      </div>

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
        <section class="card">
          <div class="card-head">
            <div>
              <h3>Per namespace</h3>
              <p class="card-sub">top 10 by findings</p>
            </div>
            <UiButton variant="mini" @click="router.push('/images')">View inventory</UiButton>
          </div>
          <div class="card-body">
            <p v-if="namespaces.length === 0" class="empty-row">No namespace data in range.</p>
            <table v-else class="tbl tbl-hover">
              <thead>
                <tr><th>Namespace</th><th class="r">Findings</th></tr>
              </thead>
              <tbody>
                <tr
                  v-for="n in namespaces"
                  :key="n.key"
                  :title="`Open findings in ${n.key}`"
                  @click="goFindings({ namespace: n.key })"
                >
                  <td class="mono-cell ns-link">{{ n.key }}<AppIcon class="cell-go" name="chevron" :size="11" /></td>
                  <td class="r mono-cell"><b>{{ fmt(n.count) }}</b></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.screen-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.screen-head h1 {
  margin: 0 0 4px;
}
.screen-sub {
  margin: 0;
  color: var(--soft);
  font-size: var(--text-body);
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* joined stat band — one card, hairline-divided cells (Nuxt stat grammar, risk-band precedent) */
.kpi-band {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.kpi-cell {
  cursor: default; /* system arrow everywhere — affordance is the chevron + wash, never the cursor */
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 14px 16px 12px;
  border: none;
  background: var(--card);
  text-align: left;
  transition: background var(--dur-quick);
}
.kpi-cell + .kpi-cell {
  border-left: 1px solid var(--line2);
}
.kpi-cell:hover {
  background: var(--control-hover-bg);
}
.kpi-cell:active {
  background: var(--control-active-bg);
}
.kpi-cell:focus-visible {
  outline: var(--focus-ring);
  outline-offset: -2px;
}
.kpi-label {
  display: flex;
  align-items: center;
  gap: 7px;
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--soft);
  font-weight: 700;
}
.kpi-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.kpi-dot-fix {
  background: var(--teal);
}
.kpi-dot-kev {
  background: var(--kev-bg);
}
.kpi-dot-disagree {
  background: var(--sev-medium-solid);
}
.kpi-dot-progress {
  background: var(--state-resolved-fg);
}
.kpi-num-alarm {
  color: var(--sev-critical-fg);
}
.signal-band {
  grid-template-columns: repeat(3, 1fr);
  margin-top: 12px;
}

/* at-rest clickability affordance (operator ruling 2026-07-10): navigating cells carry a soft
   trailing chevron that turns coral with the hover wash — hover alone is not discoverable */
.cell-go {
  color: var(--dash-muted);
  margin-left: 4px;
  transition: color var(--dur-quick);
}
.kpi-cell:hover .cell-go,
.tbl-hover tbody tr:hover .cell-go {
  color: var(--coral-text);
}

.progress-bar {
  display: flex;
  width: 100%;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  margin-top: 8px;
  background: var(--line2);
}
.progress-bar i {
  height: 100%;
}
.seg-open {
  background: var(--state-open-fg);
}
.seg-ack {
  background: var(--state-ack-fg);
}
.seg-handled {
  background: var(--state-resolved-fg);
}
.seg-stale {
  background: var(--state-stale-line);
}
.kpi-num {
  font-size: var(--text-kpi);
  font-weight: 600;
  letter-spacing: -0.03em;
  line-height: 1.05;
  margin-top: 6px;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.kpi-sub {
  font-size: var(--text-sm);
  color: var(--soft);
  font-family: var(--font-mono);
  margin-top: 7px;
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
  .kpi-band {
    grid-template-columns: repeat(2, 1fr);
  }
  .kpi-cell + .kpi-cell {
    border-left: none;
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

.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-body);
}
.tbl th {
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--soft);
  text-align: left;
  padding: 7px 8px;
  border-bottom: 1px solid var(--line2);
  background: var(--panel);
}
.tbl td {
  padding: 7px 8px;
  border-bottom: 1px solid var(--line2);
}
.tbl .r {
  text-align: right;
}
.tbl-hover tbody tr {
  cursor: default; /* arrow, not the I-beam — text stays selectable */
  transition: background var(--dur-quick);
}
.tbl-hover tbody tr:hover {
  background: var(--row-hover);
}
.tbl-hover tbody tr:active {
  background: var(--line2);
}
/* the affordance carrier — same convention as the grid's cve-link */
.ns-link {
  transition: color var(--dur-quick);
}
.tbl-hover tbody tr:hover .ns-link {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .tbl-hover tbody tr,
  .ns-link,
  .cell-go,
  .kpi-cell {
    transition: none;
  }
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
