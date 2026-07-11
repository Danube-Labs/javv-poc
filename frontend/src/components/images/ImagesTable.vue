<script setup lang="ts">
/**
 * The running-images grid (M9c slice 3) — the SAME PrimeVue DataTable grammar as the M9b
 * findings grid (`.tbl` family, hover/link/cursor rulings), only the columns differ. The
 * inventory is one committed run, fully served — sorting is client-side over those rows
 * (emitted to the parent, which sorts + slices), never a server round-trip.
 */
import Column from 'primevue/column'
import DataTable, { type DataTableSortEvent } from 'primevue/datatable'

import CountDisagree from '@/components/chips/CountDisagree.vue'
import MixBar from '@/components/dashboards/MixBar.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import type { ImageRow } from '@/stores/images'
import type { Severity } from '@/styles/tokens'
import { lastDataAt } from '@/system/freshness'

export type ImagesSortField = 'total' | 'replicas'

const props = withDefaults(
  defineProps<{
    rows: ImageRow[]
    sort: ImagesSortField | null
    order: 'asc' | 'desc'
    loading: boolean
    filtered: boolean
    /** keys from IMAGES_COLUMNS hidden via the Columns menu (Image/Findings are fixed) */
    hidden?: ReadonlySet<string>
    dense?: boolean
  }>(),
  { hidden: () => new Set<string>(), dense: true },
)

const show = (key: string) => !props.hidden.has(key)

const emit = defineEmits<{
  sort: [field: ImagesSortField]
  rowClick: [row: ImageRow]
}>()

function onSort(e: DataTableSortEvent) {
  if (typeof e.sortField === 'string') emit('sort', e.sortField as ImagesSortField)
}

const shortRepo = (r: ImageRow) => r.image_repo.split('/').at(-1) ?? r.image_repo
const registryOf = (r: ImageRow) =>
  r.image_repo.includes('/') ? r.image_repo.slice(0, r.image_repo.lastIndexOf('/')) : null
const mixOf = (r: ImageRow): Partial<Record<Severity, number>> => ({
  critical: r.crit,
  high: r.high,
  medium: r.med,
  low: r.low,
  negligible: r.negligible,
  unknown: r.unknown,
})
const nsLabel = (r: ImageRow) =>
  r.namespaces.length <= 1 ? (r.namespaces[0] ?? '-') : `${r.namespaces[0]} +${r.namespaces.length - 1}`
const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <div class="tbl-wrap">
    <DataTable
      :value="props.rows"
      lazy
      :sort-field="props.sort ?? undefined"
      :sort-order="props.order === 'desc' ? -1 : 1"
      :loading="props.loading"
      data-key="image_digest"
      :pt="{ table: { class: `tbl tbl-hover ${props.dense ? 'tbl-dense' : ''}` } }"
      @sort="onSort"
      @row-click="(e) => emit('rowClick', e.data as ImageRow)"
    >
      <Column header="Image">
        <template #body="{ data }">
          <div class="img-id">
            <span class="img-name img-link">{{ shortRepo(data) }}<AppIcon class="cell-go" name="chevron" :size="11" /></span>
            <span v-if="registryOf(data)" class="mono-cell sm img-reg">{{ registryOf(data) }}</span>
          </div>
        </template>
      </Column>
      <Column v-if="show('tag')" header="Tag">
        <template #body="{ data }">
          <span class="mono-cell sm">{{ data.tag }}</span>
        </template>
      </Column>
      <Column v-if="show('namespace')" header="Namespace">
        <template #body="{ data }">
          <span class="mono-cell sm" :title="data.namespaces.join(', ')">{{ nsLabel(data) }}</span>
        </template>
      </Column>
      <Column v-if="show('replicas')" field="replicas" sortable>
        <template #header>
          <span>Replicas<span class="th-note">at last sweep</span></span>
        </template>
        <template #body="{ data }">
          <span class="mono-cell">{{ fmt(data.replicas ?? 0) }}</span>
        </template>
      </Column>
      <Column field="total" sortable>
        <template #header>
          <span>Vulns<span class="th-note">Trivy / Grype · never summed</span></span>
        </template>
        <template #body="{ data }">
          <CountDisagree :trivy="data.trivy_count" :grype="data.grype_count" :total="data.total" />
        </template>
      </Column>
      <Column v-if="show('mix')" header="Severity mix">
        <template #body="{ data }">
          <MixBar :counts="mixOf(data)" :label="data.scanners.join('+')" class="mix-sized" />
        </template>
      </Column>
      <Column v-if="show('seen')" header="Last seen">
        <template #body="{ data }">
          <span class="mono-cell sm nowrap">{{ lastDataAt(data['@timestamp']) }}</span>
        </template>
      </Column>
      <template #empty>
        <div class="empty-row">
          {{ filtered ? 'No images match these filters.' : 'No running images in the committed inventory.' }}
        </div>
      </template>
    </DataTable>
  </div>
</template>

<style scoped>
/* the table skin (.tbl-wrap / .tbl family / th-note / empty-row) lives in base.css —
   only this grid's own cells are styled here */

.img-id {
  display: flex;
  flex-direction: column;
}
.img-name {
  display: inline-flex;
  align-items: center;
  font-weight: 600;
  color: var(--ink);
}
.img-reg {
  color: var(--soft);
}
/* the affordance carrier — identifier takes the link treatment on row hover (ruled) */
.img-link {
  transition: color var(--dur-quick);
}
:deep(.tbl-hover tbody tr:hover) .img-link {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.cell-go {
  color: var(--dash-muted);
  margin-left: 4px;
  transition: color var(--dur-quick);
}
:deep(.tbl-hover tbody tr:hover) .cell-go {
  color: var(--coral-text);
}
.mix-sized {
  min-width: 140px;
}
@media (prefers-reduced-motion: reduce) {
  :deep(.tbl-hover tbody tr),
  .img-link,
  .cell-go {
    transition: none;
  }
}
</style>
