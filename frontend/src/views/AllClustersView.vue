<script setup lang="ts">
/**
 * All clusters — fleet landing page (M9c slice 2; SCREENS §1). Same joined stat grammar as
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
import MixBar from '@/components/dashboards/MixBar.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { useAllClustersStore, type ClusterRow } from '@/stores/allClusters'
import { useClusterStore } from '@/stores/cluster'
import { useStalenessStore } from '@/stores/staleness'
import { useTimeTravelStore } from '@/stores/timeTravel'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import { CHART_SEV, type Severity } from '@/styles/tokens'
import { freshnessStatus, lastDataAt } from '@/system/freshness'

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
// health chips threshold on the live FLEET-default window (a per-cluster override is the
// banner's concern; this cross-cluster surface uses the one shared default)
const staleness = useStalenessStore()
void staleness.loadFleet()

const scanner = ref<'all' | 'trivy' | 'grype'>('all')

watch(
  () => timeTravel.t,
  (t) => void fleet.load(t),
  { immediate: true },
)

/** A cluster's server bucket count under the scanner lens — by_scanner split, never re-added. */
function bucketCount(row: ClusterRow, facet: string, key: string): number {
  const b = row.facets[facet]?.find((x) => x.key === key)
  if (!b) return 0
  return scanner.value === 'all' ? b.count : (b.by_scanner[scanner.value] ?? 0)
}
const sevCount = (row: ClusterRow, sev: Severity) => bucketCount(row, 'severity', sev)
const presentCount = (row: ClusterRow) => bucketCount(row, 'present', 'true')

/* per-row signals — all straight facet reads the row already fetched (Overview 1b analogs) */
const kevCount = (row: ClusterRow) => bucketCount(row, 'kev', 'true')
const disagreeCount = (row: ClusterRow) => bucketCount(row, 'disagree', 'true')
const fixPct = (row: ClusterRow) => {
  const present = presentCount(row)
  return present === 0 ? 0 : Math.round((bucketCount(row, 'fixable', 'true') / present) * 100)
}
function triage(row: ClusterRow) {
  const open = bucketCount(row, 'state', 'open')
  const ack = bucketCount(row, 'state', 'acknowledged')
  const stale = bucketCount(row, 'state', 'stale')
  const handled =
    bucketCount(row, 'state', 'resolved') +
    bucketCount(row, 'state', 'not_affected') +
    bucketCount(row, 'state', 'risk_accepted')
  const total = open + ack + stale + handled
  const pct = (n: number) => (total === 0 ? 0 : (n / total) * 100)
  return { open, ack, stale, handled, total, pct }
}

/** Fleet strip: per-severity server buckets added across clusters (see header). */
const fleetSev = (sev: Severity) => fleet.rows.reduce((n, r) => n + sevCount(r, sev), 0)

const needAttention = computed(
  () =>
    fleet.rows.filter(
      (r) => r.failed || freshnessStatus(r.freshness, staleness.fleetThresholdS) !== 'ok',
    ).length,
)

/** One mix bar per scanner (never merged): that scanner's by_scanner severity buckets. */
function mixFor(row: ClusterRow, sc: (typeof SCANNERS)[number]): Partial<Record<Severity, number>> {
  return Object.fromEntries(
    MIX_SEVERITIES.map((sev) => [
      sev,
      row.facets.severity?.find((x) => x.key === sev)?.by_scanner[sc] ?? 0,
    ]),
  )
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
      <div class="head-card head-card-fluid">
        <h1>All clusters</h1>
        <p class="head-note">
          <template v-if="fleet.limited">Historical fleet view — limited until the v1.1 rollup</template>
          <template v-else>
            Fleet current state · <b class="mono-cell">{{ fleet.rows.length }}</b>
            cluster{{ fleet.rows.length === 1 ? '' : 's' }}
            <template v-if="!fleet.loading && fleet.rows.length">
              · <span v-if="needAttention" class="deg-note">{{ needAttention }} need{{ needAttention === 1 ? 's' : '' }} attention</span>
              <template v-else>all healthy</template>
            </template>
          </template>
        </p>
      </div>
      <div v-if="!fleet.limited" class="head-actions">
        <UiSegControl v-model="scanner" :options="SCANNER_OPTS" />
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
      <div class="stat-band fleet-band">
        <div class="stat-cell">
          <span class="stat-label"><i class="stat-dot" style="background: var(--slate)" />clusters</span>
          <span class="stat-num">{{ fmt(fleet.rows.length) }}</span>
        </div>
        <div v-for="s in KPI_SEVERITIES" :key="s" class="stat-cell">
          <span class="stat-label"><i class="stat-dot" :style="{ background: CHART_SEV[s] }" />{{ s }}</span>
          <span class="stat-num">{{ fmt(fleetSev(s)) }}</span>
        </div>
      </div>

      <!-- flush table card (prototype fleet-card): no head, no inner panel — the table IS the card -->
      <section class="card fleet-card">
          <table class="tbl tbl-hover">
            <thead>
              <tr>
                <th>Cluster</th>
                <th class="r">Health</th>
                <th>Severity mix</th>
                <th class="r">Findings</th>
                <th class="r">KEV</th>
                <th class="r">Fix %</th>
                <th class="r">Disagree</th>
                <th class="r">Triage</th>
                <th class="r">Images</th>
                <th class="r">Replicas</th>
                <th class="r">Last sweep</th>
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
                  <div class="cluster-cell">
                    <span class="glyph" aria-hidden="true">{{ (row.cluster_name[0] ?? '?').toUpperCase() }}</span>
                    <div class="cluster-info">
                      <span class="cl-name cl-link">{{ row.cluster_name }}<AppIcon class="cell-go" name="chevron" :size="11" /></span>
                      <span v-if="row.cluster_name !== row.cluster_id" class="cl-id mono-cell">{{ row.cluster_id }}</span>
                    </div>
                  </div>
                </td>
                <td class="r"><HealthChip :rows="row.freshness" :threshold-s="staleness.fleetThresholdS" /></td>
                <td class="mix-cell">
                  <template v-if="!row.failed">
                    <MixBar
                      v-for="sc in visibleScanners"
                      :key="sc"
                      :counts="mixFor(row, sc)"
                      :label="sc"
                      class="mix-stack"
                    />
                  </template>
                  <span v-else class="row-degraded">unavailable</span>
                </td>
                <td class="r mono-cell"><b>{{ row.failed ? '—' : fmt(presentCount(row)) }}</b></td>
                <td class="r mono-cell">
                  <b :class="{ 'kev-alarm': kevCount(row) > 0 }">{{ row.failed ? '—' : fmt(kevCount(row)) }}</b>
                </td>
                <td class="r mono-cell">{{ row.failed ? '—' : `${fixPct(row)}%` }}</td>
                <td class="r mono-cell">{{ row.failed ? '—' : fmt(disagreeCount(row)) }}</td>
                <td class="r triage-cell">
                  <template v-if="!row.failed && triage(row).total > 0">
                    <span class="progress-bar" aria-hidden="true">
                      <i class="seg-open" :style="{ width: `${triage(row).pct(triage(row).open)}%` }" />
                      <i class="seg-ack" :style="{ width: `${triage(row).pct(triage(row).ack)}%` }" />
                      <i class="seg-handled" :style="{ width: `${triage(row).pct(triage(row).handled)}%` }" />
                      <i class="seg-stale" :style="{ width: `${triage(row).pct(triage(row).stale)}%` }" />
                    </span>
                    <span class="triage-pct mono-cell">{{ Math.round(triage(row).pct(triage(row).handled + triage(row).ack)) }}%</span>
                  </template>
                  <span v-else class="muted-dash">-</span>
                </td>
                <td class="r mono-cell">{{ row.imagesCount === null ? '—' : fmt(row.imagesCount) }}</td>
                <td class="r mono-cell">{{ row.replicas === null ? '—' : fmt(row.replicas) }}</td>
                <td class="r mono-cell sweep-cell">{{ lastSweep(row) ?? 'never' }}</td>
              </tr>
            </tbody>
          </table>
      </section>
      <p class="fleet-note">
        <AppIcon name="layers" :size="13" />
        Each cluster's scanner module pushes independently over HTTPS with its own API token —
        a cluster going quiet shows up here, not as missing data downstream.
      </p>
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
.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* joined stat band (Nuxt stat grammar) — fleet cells are read-only: no wash, no chevron
   (never dress a cell whose destination doesn't exist) */
/* the joined stat-band SKIN lives in base.css (issue 368) — only this screen's layout here */
.fleet-band {
  grid-template-columns: repeat(6, 1fr);
}

/* flush table card (prototype fleet-card): the table IS the card — no head, no inner panel */
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  margin-top: 16px;
}
.fleet-card {
  overflow: hidden;
}
.fleet-card .tbl th:first-child,
.fleet-card .tbl td:first-child {
  padding-left: 16px;
}
.fleet-card .tbl th:last-child,
.fleet-card .tbl td:last-child {
  padding-right: 16px;
}
.fleet-card .tbl tbody tr:last-child td {
  border-bottom: 0;
}
.deg-note {
  color: var(--health-degraded-fg);
  font-weight: 600;
}
.fleet-note {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 10px 2px 0;
  font-size: var(--text-sm);
  color: var(--soft);
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
  padding: 7px 12px;
  border-bottom: 1px solid var(--line2);
  background: var(--panel);
}
.tbl td {
  padding: 9px 12px;
  border-bottom: 1px solid var(--line2);
  vertical-align: middle;
}
/* anchored numeric columns (operator A/B ruling, sharpened live twice): shrink-to-content +
   nowrap, HAIRLINE COLUMN DIVIDERS (the stat-band grammar carried into the table), and the
   value CENTERED + weighted in its bounded cell — right-hugging regular-weight digits at the
   top of a tall row read as floating */
.tbl th + th,
.tbl td + td {
  border-left: 1px solid var(--line2);
}
/* .tbl.tbl matches the base-skin weight — this screen's centered-value ruling must outrank
   the shared right-align default */
.tbl.tbl th.r,
.tbl.tbl td.r {
  text-align: center;
  width: 1%;
  white-space: nowrap;
}
.tbl.tbl td.r {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
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

.cluster-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.glyph {
  width: 26px;
  height: 26px;
  border-radius: 7px;
  background: var(--slate);
  color: var(--side-brand-fg);
  display: grid;
  place-items: center;
  font-weight: 600;
  font-size: var(--text-body);
  flex: none;
}
.cluster-info {
  display: flex;
  flex-direction: column;
}
.cl-name {
  display: inline-flex;
  align-items: center;
  font-weight: 600;
  color: var(--ink);
}
.cl-id {
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

.mix-cell {
  min-width: 180px;
}
.mix-stack + .mix-stack {
  margin-top: 4px;
}
.muted-dash {
  color: var(--dash-muted);
}

/* per-row signals (A/B under review) — same seg colors as the Overview triage bar */
.kev-alarm {
  color: var(--sev-critical-fg);
}
.progress-bar {
  display: flex;
  width: 90px;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
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
.triage-cell {
  white-space: nowrap;
  width: 1%;
}
.triage-cell .progress-bar {
  display: inline-flex;
  vertical-align: middle;
}
.triage-pct {
  font-size: var(--text-sm);
  color: var(--soft);
  margin-left: 8px;
}
.row-degraded {
  font-size: var(--text-sm);
  color: var(--soft);
}

@media (prefers-reduced-motion: reduce) {
  .tbl-hover tbody tr,
  .cl-link {
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
