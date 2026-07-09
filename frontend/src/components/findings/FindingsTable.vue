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
  }>(),
  { hidden: () => new Set<string>(), dense: true },
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
      <Column v-if="show('component')" header="Component">
        <template #body="{ data }">
          <span class="mono-cell sm">{{ data.app ?? '-' }}</span>
        </template>
      </Column>
      <Column v-if="show('package')" header="Package">
        <template #body="{ data }">
          <span class="pkg"
            >{{ data.package_name }}<i class="pkg-type">{{ data.ptype ?? 'unknown' }}</i></span
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
      <Column v-if="show('images')" header="Images" class="r">
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
        <div class="empty-row">No findings match these filters.</div>
      </template>
    </DataTable>
  </div>
</template>

<style scoped>
.tbl-wrap {
  overflow-x: auto;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
}

/* prototype .tbl family — element selectors, so PrimeVue's internal classes don't matter */
:deep(.tbl) {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-mono-cell);
  cursor: default; /* arrow, not the I-beam — text stays selectable (operator ruling) */
}
:deep(.tbl thead th) {
  text-align: left;
  font-weight: 600;
  color: var(--soft);
  font-size: var(--text-table-header);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
  white-space: nowrap;
  font-family: var(--font-mono);
}
:deep(.tbl tbody td) {
  padding: 9px 12px;
  border-bottom: 1px solid var(--line2);
  vertical-align: middle;
}
:deep(.tbl-dense thead th) {
  padding: 8px 12px;
}
:deep(.tbl-dense tbody td) {
  padding: 7px 12px;
}
:deep(.tbl tbody tr:last-child td) {
  border-bottom: 0;
}
:deep(.tbl-hover tbody tr) {
  /* arrow cursor, not pointer — desktop-app convention (operator ruling; Linear model).
     the affordance is the hover treatment, not the hand */
  transition: background 0.12s ease-out;
}
:deep(.tbl-hover tbody tr:hover) {
  background: var(--row-hover);
}
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
:deep(.tbl-hover tbody tr:active) {
  background: var(--line2);
}
@media (prefers-reduced-motion: reduce) {
  :deep(.tbl-hover tbody tr),
  :deep(.cve-link) {
    transition: none;
  }
}
:deep(.tbl th.r),
:deep(.tbl td.r) {
  text-align: right;
}
:deep(.tbl th.c),
:deep(.tbl td.c) {
  text-align: center;
}
:deep(.mono-cell) {
  font-family: var(--font-mono);
}
:deep(.strong) {
  font-weight: 700;
}
:deep(.nowrap) {
  white-space: nowrap;
}
:deep(.img-cell) {
  display: inline-block;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
:deep(.tbl .sm) {
  font-size: var(--text-sm);
}
:deep(.th-note) {
  font-size: var(--text-dd-head);
  color: var(--soft);
  text-transform: none;
  letter-spacing: 0;
  margin-left: 5px;
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
  text-align: center;
  color: var(--soft);
  padding: 34px 12px;
  font-size: var(--text-body);
}
</style>
