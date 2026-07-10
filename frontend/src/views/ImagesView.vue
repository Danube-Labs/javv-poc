<script setup lang="ts">
/**
 * Running images — the committed-inventory surface (M9c slice 3; SCREENS-v5 §7). Rows are the
 * server's image docs verbatim: the mix bar and Findings count belong to the doc's OWN
 * scanner(s) (labeled), the D5b `T/G Δ` pair is the cross-scanner signal — never merged.
 * Fully time-travelable: the global T rides `as_of` into the same backend primitives as the
 * M8b reader; no committed inventory at T = "unknown", never an empty cluster. Image naming
 * composes `image_repo` + `tag` — no combined image_ref field exists on the docs.
 */
import { computed, watch } from 'vue'

import ScannerTag from '@/components/chips/ScannerTag.vue'
import MixBar from '@/components/dashboards/MixBar.vue'
import { useApi } from '@/composables/useApi'
import { useClusterStore } from '@/stores/cluster'
import { useImagesStore, type ImageRow } from '@/stores/images'
import { useTimeTravelStore } from '@/stores/timeTravel'
import type { Severity } from '@/styles/tokens'
import { lastDataAt } from '@/system/freshness'

const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const images = useImagesStore()
const { withGlobals } = useApi()

watch(
  () => [clusterStore.selectedId, timeTravel.t] as const,
  ([id]) => {
    if (id) void images.load(withGlobals({ cluster_id: id }))
  },
  { immediate: true },
)

/** The doc's severity buckets under canonical names — they are the doc's own scanner's. */
function mixOf(row: ImageRow): Partial<Record<Severity, number>> {
  return {
    critical: row.crit,
    high: row.high,
    medium: row.med,
    low: row.low,
    negligible: row.negligible,
    unknown: row.unknown,
  }
}

/** Registry prefix split off for the quiet second line (docker.io/library/nginx → nginx). */
const shortRepo = (repo: string) => repo.split('/').at(-1) ?? repo
const registryOf = (repo: string) => (repo.includes('/') ? repo.slice(0, repo.lastIndexOf('/')) : null)

const totalReplicas = computed(() => images.images.reduce((n, r) => n + (r.replicas ?? 0), 0))
const inventoryAt = computed(() =>
  images.inventory?.completed_at ? lastDataAt(images.inventory.completed_at) : null,
)
const fmt = (n: number) => n.toLocaleString('en-US')
const delta = (n: number) => (n > 0 ? `+${fmt(n)}` : fmt(n))
</script>

<template>
  <div class="screen">
    <div class="screen-head">
      <div>
        <h1>Running images</h1>
        <p class="screen-sub">
          <template v-if="images.inventory">
            <b class="mono-cell">{{ fmt(images.images.length) }}</b>
            image{{ images.images.length === 1 ? '' : 's' }} ·
            <b class="mono-cell">{{ fmt(totalReplicas) }}</b> replicas
            <template v-if="inventoryAt"> · inventory as of <span class="mono-cell">{{ inventoryAt }}</span></template>
          </template>
          <template v-else>the latest committed inventory, per digest</template>
        </p>
      </div>
    </div>

    <div v-if="images.loading" aria-busy="true" aria-label="Loading images">
      <div class="skel skel-card" />
    </div>

    <p v-else-if="images.failed" class="load-error" role="alert">
      Inventory unavailable. Check the backend connection.
    </p>

    <div v-else-if="images.unknown" class="first-run">
      <h2>No inventory committed{{ timeTravel.isNow ? ' yet' : ' at this point in time' }}</h2>
      <p>
        Images appear once a scanner cycle completes and certifies its inventory.
        <template v-if="!timeTravel.isNow">This T predates the first committed run.</template>
      </p>
    </div>

    <div v-else-if="images.images.length === 0" class="first-run">
      <h2>No running images</h2>
      <p>The inventory committed{{ inventoryAt ? ` at ${inventoryAt}` : '' }} is empty.</p>
    </div>

    <section v-else class="card fleet-card">
      <table class="tbl tbl-hover">
        <thead>
          <tr>
            <th>Image</th>
            <th>Tag</th>
            <th>Namespaces</th>
            <th>Severity mix</th>
            <th class="r">Findings</th>
            <th class="r">T / G · Δ</th>
            <th class="r">Replicas</th>
            <th class="r">Scanners</th>
            <th class="r">Last seen</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in images.images" :key="row.image_digest">
            <td>
              <span class="img-name">{{ shortRepo(row.image_repo) }}</span>
              <span v-if="registryOf(row.image_repo)" class="img-registry mono-cell">{{ registryOf(row.image_repo) }}</span>
            </td>
            <td class="mono-cell">{{ row.tag }}</td>
            <td class="mono-cell ns-cell" :title="row.namespaces.join(', ')">{{ row.namespaces.join(', ') }}</td>
            <td class="mix-cell">
              <MixBar :counts="mixOf(row)" :label="row.scanners.join('+')" />
            </td>
            <td class="r mono-cell"><b>{{ fmt(row.total) }}</b></td>
            <td class="r mono-cell">
              <template v-if="row.trivy_count != null && row.grype_count != null">
                {{ fmt(row.trivy_count) }} / {{ fmt(row.grype_count) }}
                · <b :class="{ 'delta-warn': row.count_delta !== 0 }">Δ {{ delta(row.count_delta ?? 0) }}</b>
              </template>
              <span v-else class="muted-dash">-</span>
            </td>
            <td class="r mono-cell">{{ fmt(row.replicas ?? 0) }}</td>
            <td class="r">
              <span class="scanner-stack">
                <ScannerTag v-for="s in row.scanners" :key="s" :name="s" />
              </span>
            </td>
            <td class="r mono-cell">{{ lastDataAt(row['@timestamp']) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
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

/* flush table card + anchored cells — the ruled all-clusters grammar */
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
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
  border-bottom: 1px solid var(--line);
  vertical-align: middle;
}
.tbl th + th,
.tbl td + td {
  border-left: 1px solid var(--line2);
}
.tbl .r {
  text-align: center;
  width: 1%;
  white-space: nowrap;
}
.tbl td.r {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.tbl-hover tbody tr {
  cursor: default;
  transition: background var(--dur-quick);
}
.tbl-hover tbody tr:hover {
  background: var(--row-hover);
}
@media (prefers-reduced-motion: reduce) {
  .tbl-hover tbody tr {
    transition: none;
  }
}

.img-name {
  display: block;
  font-weight: 600;
  color: var(--ink);
}
.img-registry {
  font-size: var(--text-sm);
  color: var(--soft);
}
.ns-cell {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mix-cell {
  min-width: 150px;
}
.delta-warn {
  color: var(--sev-medium-fg);
}
.muted-dash {
  color: var(--dash-muted);
}
.scanner-stack {
  display: inline-flex;
  gap: 4px;
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
.skel-card {
  height: 320px;
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
