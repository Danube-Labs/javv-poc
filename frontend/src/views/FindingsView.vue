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
import { useClusterStore } from '@/stores/cluster'
import { useFindingsStore, type FindingRow } from '@/stores/findings'
import { makeFiltersStore } from '@/stores/filters'

const useFindingsFilters = makeFiltersStore('findings-filters', FINDINGS_FIELDS)
const filters = useFindingsFilters()
const clusterStore = useClusterStore()
const grid = useFindingsStore()
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

watch(
  facetsQuery,
  async (q) => {
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
  },
  { immediate: true },
)

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

watch(
  rowsQuery,
  async (q, old) => {
    if (!q || JSON.stringify(q) === JSON.stringify(old)) return
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
    } else if (grid.page > 0) {
      // stale PIT cursor is the usual culprit — rebuild from page 0
      logger.warn('findings_page_failed_reset', { status: response.response?.status })
      grid.resetPaging()
    } else {
      grid.failed = true
      logger.warn('findings_search_failed', { status: response.response?.status })
    }
  },
  { immediate: true },
)

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
  // detail panel lands in M9b slice 2
  logger.debug('finding_row_clicked', { finding_key: row.finding_key })
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
          Findings unavailable — check the backend connection.
        </p>
        <FindingsTable
          :rows="grid.rows"
          :sort="grid.sort"
          :order="grid.order"
          :loading="grid.loading"
          :hidden="hiddenCols"
          :dense="dense"
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
  margin-bottom: 14px;
}
.screen-sub {
  color: var(--soft);
  font-size: var(--text-body);
  margin-top: 2px;
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
  color: var(--teal-text);
  background: var(--note-info-bg);
  border: 1px solid var(--note-info-line);
  border-radius: var(--r-sm);
  padding: 7px 11px;
  margin-bottom: 12px;
}
.load-error {
  color: var(--health-down-fg);
  font-size: var(--text-body);
  margin: 0 0 10px;
}
</style>
