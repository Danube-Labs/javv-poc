<script setup lang="ts">
/**
 * Findings screen (M9a filter module + M9b grid): one FINDINGS_FIELDS config drives FacetRail +
 * FilterBar, selections URL-synced; the lazy grid renders exactly what
 * `GET /api/v1/findings` returns (cursor paging, server total). Facet counts live from
 * `GET /api/v1/findings/facets`. Everything carries cluster_id + as_of; grid queries add
 * present=true. Detail panel + triage land in the next M9b slices.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { facetFindingsApiV1FindingsFacetsGet, searchFindingsApiV1FindingsGet } from '@/api/generated'
import type {
  FacetFindingsApiV1FindingsFacetsGetData,
  SearchFindingsApiV1FindingsGetData,
} from '@/api/generated'
import SevChip from '@/components/chips/SevChip.vue'
import FacetRail from '@/components/filters/FacetRail.vue'
import FilterBar from '@/components/filters/FilterBar.vue'
import ColumnsMenu from '@/components/findings/ColumnsMenu.vue'
import ExportDialog from '@/components/findings/ExportDialog.vue'
import BulkTriageBar from '@/components/triage/BulkTriageBar.vue'
import FindingsTable from '@/components/findings/FindingsTable.vue'
import GridPager from '@/components/findings/GridPager.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { useApi } from '@/composables/useApi'
import { buildFilterQuery } from '@/filters/buildFilterQuery'
import type { FacetsResponse } from '@/filters/facets'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { buildFindingsQuery } from '@/findings/buildFindingsQuery'
import { FINDINGS_COLUMNS } from '@/findings/columns'
import { logger } from '@/lib/logger'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useFindingsStore, type FindingRow } from '@/stores/findings'
import { makeFiltersStore } from '@/stores/filters'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'

const useFindingsFilters = makeFiltersStore('findings-filters', FINDINGS_FIELDS)
const filters = useFindingsFilters()
const auth = useAuthStore()
const clusterStore = useClusterStore()
const grid = useFindingsStore()
const timeTravel = useTimeTravelStore()
const toast = useToastStore()
const { withGlobals } = useApi()
const route = useRoute()
const router = useRouter()

const facets = ref<FacetsResponse>({})
const facetsFailed = ref(false)

filters.fromQuery(route.query)

/* ---- facets (M9a) ---- */
const facetsQuery = computed(() =>
  clusterStore.selectedId ? buildFilterQuery(FINDINGS_FIELDS, filters.selections, withGlobals()) : null,
)

async function loadFacets(q: typeof facetsQuery.value) {
  if (!q) return
  const response = await facetFindingsApiV1FindingsFacetsGet({
    // builder output is a generic param record; the endpoint type is the precise contract
    query: q as FacetFindingsApiV1FindingsFacetsGetData['query'],
  })
  if (response.response?.ok && response.data) {
    facets.value = (response.data as { facets: FacetsResponse }).facets
    facetsFailed.value = false
  } else {
    facetsFailed.value = true
    logger.warn('findings_facets_failed', { status: response.response?.status })
  }
}
watch(facetsQuery, (q) => void loadFacets(q), { immediate: true })

/* ---- grid rows (M9b) ---- */
// filters or globals changed → any held cursor belongs to the old query: back to page 0
watch(facetsQuery, (q, old) => {
  if (old && JSON.stringify(q) !== JSON.stringify(old)) grid.resetPaging()
})

const rowsQuery = computed(() =>
  clusterStore.selectedId
    ? buildFindingsQuery(FINDINGS_FIELDS, filters.selections, withGlobals(), {
        sort: grid.sort,
        order: grid.order,
        size: grid.size,
        cursor: grid.activeCursor,
      })
    : null,
)

async function loadRows(q: typeof rowsQuery.value) {
  if (!q) return
  grid.loading = true
    const response = await searchFindingsApiV1FindingsGet({
      query: q as SearchFindingsApiV1FindingsGetData['query'],
    })
    grid.loading = false
    if (response.response?.ok && response.data) {
      const body = response.data as {
        data: FindingRow[]
        total: { value: number }
        next_cursor: string | null
      }
      grid.setResult(body.data, body.total.value, body.next_cursor)
      grid.failed = false
      grid.failedNotSupportedAtPastT = false
    } else if (grid.page > 0) {
      // stale PIT cursor is the usual culprit — rebuild from page 0
      logger.warn('findings_page_failed_reset', { status: response.response?.status })
      grid.resetPaging()
  } else {
    grid.failed = true
    grid.failedNotSupportedAtPastT = response.response?.status === 501
    logger.warn('findings_search_failed', { status: response.response?.status })
  }
}
watch(
  rowsQuery,
  (q, old) => {
    if (JSON.stringify(q) === JSON.stringify(old)) return
    void loadRows(q)
  },
  { immediate: true },
)

/** A bulk apply changed rows under the current lens — reload both surfaces in place. */
function refreshAfterBulk(count: number) {
  toast.success(`Bulk triage applied · ${count.toLocaleString('en-US')} findings`)
  grid.resetPaging()
  void loadRows(rowsQuery.value)
  void loadFacets(facetsQuery.value)
}

/* ---- URL sync (M9a) ---- */
watch(
  () => filters.toQuery(),
  (q) => {
    void router.replace({ query: q })
  },
)
watch(
  () => route.query,
  (q) => {
    if (JSON.stringify(filters.toQuery()) !== JSON.stringify(q)) filters.fromQuery(q)
  },
)

function openFinding(row: FindingRow) {
  logger.debug('finding_row_clicked', { finding_key: row.finding_key })
  void router.push({
    name: 'finding',
    params: { cveId: row.cve_id },
    // identity = (cve_id, image_digest); scanner + package keep continuity with the clicked row
    query: {
      digest: String(row.image_digest ?? ''),
      scanner: row.scanner,
      pkg: row.package_name,
      ver: row.installed_version ?? '',
    },
  })
}

/* ---- column visibility + density (Columns menu), persisted per browser ---- */
const COLS_KEY = 'javv.findings.hidden_cols'
const DENSE_KEY = 'javv.findings.dense'
const hiddenCols = ref<Set<string>>(new Set(JSON.parse(localStorage.getItem(COLS_KEY) ?? '[]')))
const dense = ref(localStorage.getItem(DENSE_KEY) !== 'false')

function toggleCol(key: string) {
  const next = new Set(hiddenCols.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  hiddenCols.value = next
  localStorage.setItem(COLS_KEY, JSON.stringify([...next]))
}
function setDense(value: boolean) {
  dense.value = value
  localStorage.setItem(DENSE_KEY, String(value))
}
</script>

<template>
  <div class="screen">
    <div class="screen-head">
      <div>
        <h1>Findings</h1>
        <p class="screen-sub">
          <b>{{ grid.total.toLocaleString('en-US') }}</b> findings · kept per-scanner, no cross-merge
        </p>
      </div>
    </div>

    <div class="findings-layout">
      <div class="rail-col">
        <div class="facet-search">
          <AppIcon name="search" :size="14" />
          <input
            :value="filters.selections.q?.[0] ?? ''"
            placeholder="CVE, image, namespace…"
            aria-label="Search findings (contains match)"
            @keydown.enter="filters.setText('q', ($event.target as HTMLInputElement).value)"
          />
        </div>
      <FacetRail
        :fields="FINDINGS_FIELDS"
        :selections="filters.selections"
        :facets="facets"
        @toggle="filters.toggle"
      >
        <template #value="{ field, value, label }">
          <SevChip v-if="field.key === 'severity'" :level="value" :dot="true" />
          <template v-else>{{ label }}</template>
        </template>
      </FacetRail>
      </div>

      <div class="findings-main">
        <div class="toolbar-row">
          <FilterBar
            :fields="FINDINGS_FIELDS"
            :selections="filters.selections"
            :facets="facets"
            @toggle="filters.toggle"
            @set-text="filters.setText"
            @clear-field="filters.clearField"
            @clear-all="filters.clearAll"
          />
          <ExportDialog
            :fields="FINDINGS_FIELDS"
            :selections="filters.selections"
            :historical="timeTravel.t !== null"
          />
          <BulkTriageBar
            :fields="FINDINGS_FIELDS"
            :selections="filters.selections"
            :total="grid.total"
            :can-triage="auth.hasCapability('can_triage')"
            :can-accept-final="auth.hasCapability('can_accept_audit_final')"
            :historical="timeTravel.t !== null"
            @applied="refreshAfterBulk"
          />
          <ColumnsMenu
            :cols="FINDINGS_COLUMNS"
            :hidden="hiddenCols"
            :dense="dense"
            @toggle-col="toggleCol"
            @update:dense="setDense"
          />
        </div>
        <div class="server-note">
          <AppIcon name="layers" :size="13" />
          All sort / filter / facet counts computed server-side via OpenSearch aggregations
        </div>

        <p v-if="grid.failed || facetsFailed" class="load-error" role="alert">
          <template v-if="grid.failedNotSupportedAtPastT">
            This filter isn't answerable at a past point in time — return to now, or drop the
            search/attribute filters.
          </template>
          <template v-else>Findings unavailable — check the backend connection.</template>
        </p>
        <FindingsTable
          :rows="grid.rows"
          :sort="grid.sort"
          :order="grid.order"
          :loading="grid.loading"
          :hidden="hiddenCols"
          :dense="dense"
          :filtered="Object.values(filters.selections).some((v) => v.length > 0)"
          @sort="grid.setSort"
          @row-click="openFinding"
        />
        <GridPager
          :total="grid.total"
          :page="grid.page"
          :size="grid.size"
          :shown="grid.rows.length"
          :has-prev="grid.hasPrev"
          :has-next="grid.hasNext"
          @prev="grid.goPrev()"
          @next="grid.goNext()"
          @update:size="grid.setSize"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.screen-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-6); /* the page band boundary — generous */
}
.screen-sub {
  color: var(--soft);
  font-size: var(--text-body);
  margin-top: 2px;
}
.rail-col {
  flex: none;
  width: var(--facet-rail-w);
}
.rail-col > :last-child {
  width: 100%;
}
/* prototype .facet-search on tokens — exact-match CVE lookup for triage */
.facet-search {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--line);
  border-radius: var(--r);
  background: var(--card);
  box-shadow: var(--shadow);
  padding: 9px 12px;
  color: var(--soft);
  margin-bottom: 10px;
}
.facet-search:focus-within {
  border-color: var(--coral);
}
.facet-search input {
  border: 0;
  background: transparent;
  outline: none;
  flex: 1;
  min-width: 0;
  font-family: var(--font-ui);
  font-size: var(--text-mono-cell);
  color: var(--ink);
}
.findings-layout {
  display: flex;
  gap: var(--grid-gap);
  align-items: flex-start;
}
.findings-main {
  flex: 1;
  min-width: 0;
}
.toolbar-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: var(--space-2); /* toolbar/note/table are ONE functional group */
}
.toolbar-row > :first-child {
  flex: 1;
}
.server-note {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  /* prose is INK — never same-hue text on a tinted panel; teal lives in the icon only */
  color: var(--ink);
  background: var(--note-info-bg);
  border: 1px solid var(--note-info-line);
  border-radius: var(--r-sm);
  padding: 7px 11px;
  margin-bottom: var(--space-2); /* note belongs to the table cluster — tight */
}
.server-note svg {
  color: var(--teal);
  flex: none;
}
.load-error {
  color: var(--health-down-fg);
  font-size: var(--text-body);
  margin: 0 0 10px;
}
</style>
