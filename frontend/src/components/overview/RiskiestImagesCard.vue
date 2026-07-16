<script setup lang="ts">
/**
 * Overview "Riskiest images" card (B specimen of the Scan-activity replacement A/B): top 10
 * running images ranked by the server's per-image severity buckets under the scanner lens —
 * critical first, then high (ties broken down the ramp). Every number is the images read's
 * server-decorated `severity_by_scanner`; the lens picks a scanner's buckets, `all` adds the
 * per-scanner counts (additive, same grammar as the fleet strip — never a cross-scanner dedupe).
 * Rows click through to the image detail.
 */
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'

import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { fmt, type ScannerLens } from '@/lib/scannerLens'
import { useClusterStore } from '@/stores/cluster'
import { useImagesStore, type ImageRow } from '@/stores/images'
import { useTimeTravelStore } from '@/stores/timeTravel'

const RANK_KEYS = ['crit', 'high', 'med', 'low'] as const

const props = defineProps<{ scanner: ScannerLens }>()

const router = useRouter()
const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const images = useImagesStore()

watch(
  () => [clusterStore.selectedId, timeTravel.t] as const,
  ([id, t]) => {
    if (!id) return
    void images.load({ cluster_id: id, ...(t ? { as_of: t } : {}) })
  },
  { immediate: true },
)

/** A row's severity bucket under the lens: one scanner's committed counts, or their sum. */
function sev(row: ImageRow, key: (typeof RANK_KEYS)[number]): number {
  const per = row.severity_by_scanner ?? {}
  if (props.scanner !== 'all') return per[props.scanner]?.[key] ?? 0
  return Object.values(per).reduce((n, b) => n + (b[key] ?? 0), 0)
}

const rows = computed(() =>
  images.images
    .map((r) => ({ row: r, rank: RANK_KEYS.map((k) => sev(r, k)) }))
    .filter((x) => x.rank.some((n) => n > 0))
    .sort((a, b) => {
      for (let i = 0; i < a.rank.length; i++) {
        if (a.rank[i] !== b.rank[i]) return (b.rank[i] ?? 0) - (a.rank[i] ?? 0)
      }
      return 0
    })
    .slice(0, 10),
)

function open(row: ImageRow) {
  void router.push({
    path: `/images/${encodeURIComponent(row.image_digest)}`,
    query: { repo: row.image_repo, tag: row.tag },
  })
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <div>
        <h3>Riskiest images</h3>
        <p class="card-sub">top 10 by critical, then high</p>
      </div>
      <UiButton variant="mini" @click="router.push('/images')">View inventory</UiButton>
    </div>
    <div class="card-body">
      <p v-if="rows.length === 0" class="empty-row">No image findings in the running inventory.</p>
      <table v-else class="tbl tbl-hover">
        <thead>
          <tr>
            <th>Image</th>
            <th class="r">Critical</th>
            <th class="r">High</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="x in rows"
            :key="x.row.image_digest"
            :title="`Open ${x.row.image_repo}:${x.row.tag}`"
            @click="open(x.row)"
          >
            <td class="mono-cell img-link">
              {{ x.row.image_repo }}:{{ x.row.tag
              }}<AppIcon class="cell-go" name="chevron" :size="11" />
            </td>
            <td class="r mono-cell">
              <b :class="{ 'crit-alarm': (x.rank[0] ?? 0) > 0 }">{{ fmt(x.rank[0] ?? 0) }}</b>
            </td>
            <td class="r mono-cell"><b>{{ fmt(x.rank[1] ?? 0) }}</b></td>
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
.crit-alarm {
  color: var(--sev-critical-fg);
}
/* the affordance carrier — same convention as the grid's cve-link */
.img-link {
  transition: color var(--dur-quick);
}
.tbl-hover tbody tr:hover .img-link {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .tbl-hover tbody tr,
  .img-link {
    transition: none;
  }
}
</style>
