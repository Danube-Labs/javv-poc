<script setup lang="ts">
/**
 * The findings grid (prototype screens-findings.jsx table + `.tbl` CSS; D27): PrimeVue
 * DataTable in LAZY mode — it renders exactly the rows the server returned; sorting emits an
 * event and the parent refetches. Nothing is sorted, counted, or paged client-side.
 *
 * Sortable columns = the server's sort whitelist only (severity_rank, epss — bolt README
 * 2026-07-09); the prototype's client-side sort on cve/state/assignee has no server field.
 * Per-scanner rows are distinct (one scanner tag per row, disagree flagged) — never merged.
 */
import Column from 'primevue/column'
import DataTable, { type DataTableSortEvent } from 'primevue/datatable'

import DisagreementBadge from '@/components/chips/DisagreementBadge.vue'
import EpssBar from '@/components/chips/EpssBar.vue'
import KevTag from '@/components/chips/KevTag.vue'
import SevChip from '@/components/chips/SevChip.vue'
import SlaCell from '@/components/chips/SlaCell.vue'
import StateTag from '@/components/chips/StateTag.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import type { SortField, SortOrder } from '@/findings/buildFindingsQuery'
import type { FindingRow } from '@/stores/findings'

const props = withDefaults(
  defineProps<{
    rows: FindingRow[]
    sort: SortField
    order: SortOrder
    loading: boolean
    /** keys from FINDINGS_COLUMNS hidden via the Columns menu (cve/severity/state are fixed) */
    hidden?: ReadonlySet<string>
    dense?: boolean
    /** any filter active? drives filtered-empty vs first-run empty copy */
    filtered?: boolean
  }>(),
  { hidden: () => new Set<string>(), dense: true, filtered: false },
)

const show = (key: string) => !props.hidden.has(key)

const emit = defineEmits<{
  sort: [field: SortField]
  rowClick: [row: FindingRow]
}>()

function onSort(e: DataTableSortEvent) {
  if (typeof e.sortField === 'string') emit('sort', e.sortField as SortField)
}

const shortImage = (r: FindingRow) => `${(r.image_repo ?? '').split('/').pop()}${r.tag ? ':' + r.tag : ''}`
const nsLabel = (r: FindingRow): string => {
  const ns = Array.isArray(r.namespaces) ? (r.namespaces as string[]) : []
  if (ns.length === 0) return '-'
  return ns.length === 1 ? ns[0]! : `${ns[0]} +${ns.length - 1}`
}
</script>

<template>
  <div class="tbl-wrap">
    <DataTable
      :value="props.rows"
      lazy
      :sort-field="props.sort"
      :sort-order="props.order === 'desc' ? -1 : 1"
      :loading="props.loading"
      data-key="finding_key"
      :pt="{ table: { class: `tbl tbl-hover ${props.dense ? 'tbl-dense' : ''}` } }"
      @sort="onSort"
      @row-click="(e) => emit('rowClick', e.data as FindingRow)"
    >
      <Column header="Vulnerability">
        <template #body="{ data }">
          <span class="mono-cell strong nowrap cve-link">{{ data.cve_id }}</span>
        </template>
      </Column>
      <Column field="severity_rank" header="Severity" sortable>
        <template #body="{ data }">
          <SevChip :level="data.severity_canonical" />
        </template>
      </Column>
      <Column v-if="show('epss')" field="epss" sortable class="r">
        <template #header>
          <span>EPSS<span class="th-note">via Grype</span></span>
        </template>
        <template #body="{ data }">
          <EpssBar :v="data.epss" />
        </template>
      </Column>
      <Column v-if="show('kev')" header="KEV" class="c">
        <template #body="{ data }">
          <KevTag :on="data.kev === true" />
        </template>
      </Column>
      <Column v-if="show('package')" header="Package">
        <template #body="{ data }">
          <span class="pkg" :title="data.package_name"
            ><em class="pkg-name">{{ data.package_name }}</em><i class="pkg-type">{{ data.ptype ?? 'unknown' }}</i></span
          >
        </template>
      </Column>
      <Column v-if="show('current')" header="Current">
        <template #body="{ data }">
          <span class="mono-cell sm ver-cur">{{ data.installed_version ?? '-' }}</span>
        </template>
      </Column>
      <Column v-if="show('fixed')" header="Fixed">
        <template #body="{ data }">
          <span v-if="data.fixed_version" class="mono-cell sm ver-fix">{{ data.fixed_version }}</span>
          <span v-else class="ver-none">no fix</span>
        </template>
      </Column>
      <Column v-if="show('image')" header="Image">
        <template #body="{ data }">
          <span class="mono-cell sm img-cell" :title="data.image_repo">{{ shortImage(data) }}</span>
        </template>
      </Column>
      <Column v-if="show('namespace')" header="Namespace">
        <template #body="{ data }">
          <span class="mono-cell sm ns-cell" :title="Array.isArray(data.namespaces) ? data.namespaces.join(', ') : ''">{{ nsLabel(data) }}</span>
        </template>
      </Column>
      <Column v-if="show('images')" header="Affected" class="r">
        <template #body="{ data }">
          <span class="mono-cell sm">{{ data.images_affected ?? '-' }}</span>
        </template>
      </Column>
      <Column v-if="show('scanner')" header="Scanner">
        <template #body="{ data }">
          <span class="scanner-stack">
            <ScannerTag :name="data.scanner" />
            <DisagreementBadge v-if="data.disagree" />
          </span>
        </template>
      </Column>
      <Column v-if="show('sla')" header="SLA" class="c">
        <template #body="{ data }">
          <SlaCell :due-at="data.due_at" :overdue="data.overdue === true" />
        </template>
      </Column>
      <Column header="State">
        <template #body="{ data }">
          <StateTag :state="data.state" />
        </template>
      </Column>
      <Column v-if="show('assignee')" header="Assignee">
        <template #body="{ data }">
          <span class="sm">{{ data.assignee ?? '-' }}</span>
        </template>
      </Column>
      <template #empty>
        <div class="empty-row">
          {{ filtered ? 'No findings match these filters.' : 'No findings yet — the first committed scan populates this grid.' }}
        </div>
      </template>
    </DataTable>
  </div>
</template>

<style scoped>
/* the table skin (.tbl-wrap / .tbl family / th-note / empty-row) lives in base.css —
   only this grid's own cells and chips are styled here */
/* the affordance carrier: the identifier reads as a link once the row is live (research: link
   cells > loud row hovers on dense tables) */
:deep(.cve-link) {
  transition: color 0.12s ease-out;
}
:deep(.tbl-hover tbody tr:hover .cve-link) {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  :deep(.cve-link) {
    transition: none;
  }
}
:deep(.img-cell) {
  display: inline-block;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
:deep(.ver-cur) {
  color: var(--soft);
}
:deep(.ver-fix) {
  color: var(--teal-text);
}
:deep(.ver-none) {
  color: var(--ver-none-fg);
  font-style: italic;
}
:deep(.pkg) {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
:deep(.pkg-name) {
  font-style: normal;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:deep(.ns-cell) {
  display: inline-block;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
:deep(.pkg-type) {
  font-family: var(--font-mono);
  font-size: var(--text-chip-sm);
  font-style: normal;
  color: var(--soft);
  background: var(--line2);
  padding: 2px 5px;
  border-radius: 4px;
  text-transform: lowercase;
}
:deep(.scanner-stack) {
  display: inline-flex;
  gap: 4px;
}
.empty-row {
  padding: 34px 12px; /* the primary grid breathes more than the skin default */
}
</style>
