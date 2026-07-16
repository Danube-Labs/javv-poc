<script setup lang="ts">
/**
 * Overview "Top components" card (A specimen of the Scan-activity replacement A/B — the
 * prototype card cut at M9c for a missing agg, restored): top packages by finding rows, each
 * with the SERVER's per-scanner unique-CVE count. The lens picks a scanner's uniques; `all`
 * adds them (additive, like every facet) — a cross-scanner distinct count would be a merge.
 * A now-only read (the route 422s at a past T — the card says so instead of guessing).
 * Rows click through to the findings grid contains-filtered on the package.
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { client } from '@/api/client'
import { topComponentsFindingsApiV1FindingsTopComponentsGet } from '@/api/generated'
import AppIcon from '@/components/ui/AppIcon.vue'
import { fmt, type ScannerLens } from '@/lib/scannerLens'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'

interface ComponentRow {
  package_name: string
  count: number
  unique_cves_by_scanner: Record<string, number>
}

const props = defineProps<{ scanner: ScannerLens }>()

const router = useRouter()
const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()

const rows = ref<ComponentRow[]>([])
const failed = ref(false)

watch(
  () => [clusterStore.selectedId, timeTravel.t] as const,
  async ([id, t]) => {
    if (!id || t !== null) return // now-only read — the template shows the rewound note
    const { data, response } = await topComponentsFindingsApiV1FindingsTopComponentsGet({
      client,
      query: { cluster_id: id } as never,
    })
    failed.value = !response?.ok
    if (response?.ok && data) {
      rows.value = (data as { components: ComponentRow[] }).components ?? []
    } else {
      logger.warn('top_components_load_failed', { status: response?.status })
    }
  },
  { immediate: true },
)

/** The lens count: one scanner's unique CVEs, or the per-scanner sum (never a cross-scanner
 * distinct count — the server doesn't compute one). */
function uniques(row: ComponentRow, scanner: ScannerLens): number {
  if (scanner !== 'all') return row.unique_cves_by_scanner[scanner] ?? 0
  return Object.values(row.unique_cves_by_scanner).reduce((n, v) => n + v, 0)
}

/** The server picks the top-10 SET by finding rows; the display orders it by the lens's
 * unique count so the column reads as the ranking the subtitle claims. */
const sorted = computed(() =>
  [...rows.value].sort((a, b) => uniques(b, props.scanner) - uniques(a, props.scanner)),
)

function goFindings(pkg: string) {
  void router.push({ path: '/findings', query: { q: pkg } })
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <div>
        <h3>Top components</h3>
        <p class="card-sub">by unique vulnerabilities</p>
      </div>
    </div>
    <div class="card-body">
      <p v-if="!timeTravel.isNow" class="empty-row">
        Component ranking is a current-state read — unavailable at a rewound T.
      </p>
      <p v-else-if="failed" class="empty-row" role="alert">Component ranking unavailable.</p>
      <p v-else-if="rows.length === 0" class="empty-row">No component data yet.</p>
      <table v-else class="tbl tbl-hover">
        <thead>
          <tr>
            <th>Component</th>
            <th class="r">Unique CVEs</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in sorted"
            :key="c.package_name"
            :title="`Open findings mentioning ${c.package_name}`"
            @click="goFindings(c.package_name)"
          >
            <td class="mono-cell pkg-link">
              {{ c.package_name }}<AppIcon class="cell-go" name="chevron" :size="11" />
            </td>
            <td class="r mono-cell">
              <b>{{ fmt(uniques(c, props.scanner)) }}</b>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
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
.pkg-link {
  transition: color var(--dur-quick);
}
.tbl-hover tbody tr:hover .pkg-link {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .tbl-hover tbody tr,
  .pkg-link {
    transition: none;
  }
}
</style>
