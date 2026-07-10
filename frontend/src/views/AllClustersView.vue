<script setup lang="ts">
/**
 * All clusters — fleet landing page (M9c slice 2; SCREENS-v5 §1). Same joined stat grammar as
 * Overview. Every per-cluster number is a server aggregation (facets/freshness/inventory, one
 * set per row); the fleet strip adds those server buckets ACROSS CLUSTERS — the only roll-up
 * available before the v1.1 metrics rollup — never across scanners (the seg lens picks the
 * server's by_scanner split, exactly like Overview). I3: at T<now the store goes `limited`,
 * the screen renders LimitedHistoricalNotice, and no query is emitted (unit-guarded).
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import HealthChip from '@/components/chips/HealthChip.vue'
import LimitedHistoricalNotice from '@/components/dashboards/LimitedHistoricalNotice.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { useAllClustersStore, type ClusterRow } from '@/stores/allClusters'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import { CHART_SEV, type Severity } from '@/styles/tokens'
import { lastDataAt } from '@/system/freshness'

const KPI_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'negligible']
const MIX_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'negligible', 'unknown']
const SCANNERS = ['trivy', 'grype'] as const
const SCANNER_OPTS = [
  { value: 'all', label: 'All scanners' },
  { value: 'trivy', label: 'trivy' },
  { value: 'grype', label: 'grype' },
] as const

const router = useRouter()
const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const fleet = useAllClustersStore()

const scanner = ref<'all' | 'trivy' | 'grype'>('all')

watch(
  () => timeTravel.t,
  (t) => void fleet.load(t),
  { immediate: true },
)

/** A cluster's server bucket count under the scanner lens — by_scanner split, never re-added. */
function sevCount(row: ClusterRow, sev: Severity): number {
  const b = row.facets.severity?.find((x) => x.key === sev)
  if (!b) return 0
  return scanner.value === 'all' ? b.count : (b.by_scanner[scanner.value] ?? 0)
}
function presentCount(row: ClusterRow): number {
  const b = row.facets.present?.find((x) => x.key === 'true')
  if (!b) return 0
  return scanner.value === 'all' ? b.count : (b.by_scanner[scanner.value] ?? 0)
}

/** Fleet strip: per-severity server buckets added across clusters (see header). */
const fleetSev = (sev: Severity) => fleet.rows.reduce((n, r) => n + sevCount(r, sev), 0)

/** One mix bar per scanner (never merged): proportional segments of that scanner's buckets. */
function mixFor(row: ClusterRow, sc: (typeof SCANNERS)[number]) {
  const counts = MIX_SEVERITIES.map((sev) => ({
    sev,
    n: row.facets.severity?.find((x) => x.key === sev)?.by_scanner[sc] ?? 0,
  }))
  const total = counts.reduce((n, c) => n + c.n, 0)
  if (total === 0) return null
  return counts.filter((c) => c.n > 0).map((c) => ({ sev: c.sev, pct: (c.n / total) * 100 }))
}
const visibleScanners = computed(() =>
  scanner.value === 'all' ? SCANNERS : ([scanner.value] as const),
)

const lastSweep = (row: ClusterRow) => {
  const latest = row.freshness
    .map((r) => r.last_ingest_at)
    .filter((v): v is string => v !== null)
    .sort()
    .at(-1)
  return latest ? lastDataAt(latest) : null
}

function open(row: ClusterRow) {
  clusterStore.select(row.cluster_id)
  void router.push('/overview')
}
const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <div class="screen">
    <div class="screen-head">
      <div>
        <h1>All clusters</h1>
        <p class="screen-sub">
          Fleet current state · <b class="mono-cell">{{ fleet.rows.length }}</b>
          cluster{{ fleet.rows.length === 1 ? '' : 's' }}
        </p>
      </div>
      <div v-if="!fleet.limited" class="head-actions">
        <UiSegControl v-model="scanner" tone="neutral" :options="SCANNER_OPTS" />
      </div>
    </div>

    <LimitedHistoricalNotice v-if="fleet.limited" />

    <div v-else-if="fleet.loading" aria-busy="true" aria-label="Loading clusters">
      <div class="skel skel-band" />
      <div class="skel skel-card" />
    </div>

    <p v-else-if="fleet.failed" class="load-error" role="alert">
      Cluster list unavailable. Check the backend connection.
    </p>

    <div v-else-if="fleet.rows.length === 0" class="first-run">
      <h2>No clusters yet</h2>
      <p>
        A cluster appears here once its scanner token is minted and the first sweep lands.
        Tokens are minted in Settings.
      </p>
    </div>

    <template v-else>
      <!-- fleet strip: same joined grammar as Overview, read-only (a fleet severity has no
           single destination — findings are per-cluster; rows below are the drill-down) -->
      <div class="kpi-band fleet-band">
        <div class="kpi-cell kpi-static">
          <span class="kpi-label"><i class="kpi-dot kpi-dot-clusters" />clusters</span>
          <span class="kpi-num">{{ fmt(fleet.rows.length) }}</span>
        </div>
        <div v-for="s in KPI_SEVERITIES" :key="s" class="kpi-cell kpi-static">
          <span class="kpi-label"><i class="kpi-dot" :style="{ background: CHART_SEV[s] }" />{{ s }}</span>
          <span class="kpi-num">{{ fmt(fleetSev(s)) }}</span>
        </div>
      </div>

      <section class="card">
        <div class="card-head">
          <div>
            <h3>Clusters</h3>
            <p class="card-sub">a row opens that cluster's overview</p>
          </div>
        </div>
        <div class="card-body">
          <table class="tbl tbl-hover">
            <thead>
              <tr>
                <th>Cluster</th>
                <th>Health</th>
                <th>Severity mix</th>
                <th class="r">Findings</th>
                <th class="r">Images</th>
                <th class="r">Replicas</th>
                <th>Last sweep</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in fleet.rows"
                :key="row.cluster_id"
                :title="`Open ${row.cluster_name} overview`"
                @click="open(row)"
              >
                <td>
                  <span class="cl-name cl-link">{{ row.cluster_name }}<AppIcon class="cell-go" name="chevron" :size="11" /></span>
                  <span v-if="row.cluster_name !== row.cluster_id" class="cl-id mono-cell">{{ row.cluster_id }}</span>
                </td>
                <td><HealthChip :rows="row.freshness" /></td>
                <td class="mix-cell">
                  <template v-if="!row.failed">
                    <div v-for="sc in visibleScanners" :key="sc" class="mix-row">
                      <span class="mix-scanner">{{ sc }}</span>
                      <span v-if="mixFor(row, sc)" class="mix-bar">
                        <i
                          v-for="seg in mixFor(row, sc)"
                          :key="seg.sev"
                          :style="{ width: `${seg.pct}%`, background: CHART_SEV[seg.sev] }"
                        />
                      </span>
                      <span v-else class="muted-dash">-</span>
                    </div>
                  </template>
                  <span v-else class="row-degraded">unavailable</span>
                </td>
                <td class="r mono-cell"><b>{{ row.failed ? '—' : fmt(presentCount(row)) }}</b></td>
                <td class="r mono-cell">{{ row.imagesCount === null ? '—' : fmt(row.imagesCount) }}</td>
                <td class="r mono-cell">{{ row.replicas === null ? '—' : fmt(row.replicas) }}</td>
                <td class="mono-cell">{{ lastSweep(row) ?? 'never' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
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

/* joined stat band (Nuxt stat grammar) — fleet cells are read-only: no wash, no chevron
   (never dress a cell whose destination doesn't exist) */
.kpi-band {
  display: grid;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.fleet-band {
  grid-template-columns: repeat(6, 1fr);
}
.kpi-cell {
  cursor: default;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 14px 16px 12px;
  border: none;
  background: var(--card);
  text-align: left;
}
.kpi-cell + .kpi-cell {
  border-left: 1px solid var(--line2);
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
.kpi-dot-clusters {
  background: var(--slate);
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

.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  margin-top: 16px;
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
  padding: 9px 8px;
  border-bottom: 1px solid var(--line2);
  vertical-align: top;
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

.cl-name {
  display: inline-flex;
  align-items: center;
  font-weight: 600;
  color: var(--ink);
}
.cl-id {
  display: block;
  font-size: var(--text-sm);
  color: var(--soft);
  margin-top: 2px;
}
/* the affordance carrier — same convention as the grid's cve-link */
.cl-link {
  transition: color var(--dur-quick);
}
.tbl-hover tbody tr:hover .cl-link {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.cell-go {
  color: var(--dash-muted);
  margin-left: 4px;
  transition: color var(--dur-quick);
}
.tbl-hover tbody tr:hover .cell-go {
  color: var(--coral-text);
}

.mix-cell {
  min-width: 180px;
}
.mix-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.mix-row + .mix-row {
  margin-top: 4px;
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
.row-degraded {
  font-size: var(--text-sm);
  color: var(--soft);
}

@media (prefers-reduced-motion: reduce) {
  .tbl-hover tbody tr,
  .cl-link,
  .cell-go {
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
