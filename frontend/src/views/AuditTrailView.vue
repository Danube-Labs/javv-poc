<script setup lang="ts">
/**
 * Audit log screen (M9d slice 1; SCREENS-v5 §10): the D32 stream on the prototype's table
 * grammar (screens-audit.jsx, operator ruling 2026-07-12) behind the shared M9a filter module
 * — one AUDIT_FIELDS config drives FacetRail + FilterBar, selections URL-synced; counts come
 * live from GET /api/v1/audit/facets. The grid is the shared cursor-stack pager (GridPager)
 * over GET /api/v1/audit; every read carries cluster_id + as_of (D28: a rewound T bounds the
 * log). Click-through only where entity_type=="finding" (A-5), through the row's read-time
 * decoration — an aged-out finding row stays inert and honest.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { auditFacetsApiV1AuditFacetsGet, readAuditLogApiV1AuditGet } from '@/api/generated'
import type {
  AuditFacetsApiV1AuditFacetsGetData,
  ReadAuditLogApiV1AuditGetData,
} from '@/api/generated'
import { AUDIT_FIELDS } from '@/audit/fields.config'
import AuditTable from '@/components/audit/AuditTable.vue'
import AuditLens from '@/components/dashboards/AuditLens.vue'
import FacetRail from '@/components/filters/FacetRail.vue'
import FilterBar from '@/components/filters/FilterBar.vue'
import GridPager from '@/components/findings/GridPager.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { useApi } from '@/composables/useApi'
import { buildFilterQuery } from '@/filters/buildFilterQuery'
import type { FacetsResponse } from '@/filters/facets'
import { logger } from '@/lib/logger'
import { useAuditStore, type AuditEvent } from '@/stores/audit'
import { useClusterStore } from '@/stores/cluster'
import { makeFiltersStore } from '@/stores/filters'
import { useToastStore } from '@/stores/toast'
import { keepTT, stripTT } from '@/system/timeTravelUrl'

const useAuditFilters = makeFiltersStore('audit-filters', AUDIT_FIELDS)
const filters = useAuditFilters()
const grid = useAuditStore()
const clusterStore = useClusterStore()
const { withGlobals } = useApi()
const route = useRoute()
const router = useRouter()

filters.fromQuery(route.query)

/* ---- facets (M9a module; audit rework — live rail counts) ---- */
const facets = ref<FacetsResponse>({})
const facetsFailed = ref(false)

const facetsQuery = computed(() =>
  clusterStore.selectedId ? buildFilterQuery(AUDIT_FIELDS, filters.selections, withGlobals()) : null,
)

async function loadFacets(q: typeof facetsQuery.value) {
  if (!q) return
  const response = await auditFacetsApiV1AuditFacetsGet({
    query: q as AuditFacetsApiV1AuditFacetsGetData['query'],
  })
  if (response.response?.ok && response.data) {
    facets.value = (response.data as { facets: FacetsResponse }).facets
    facetsFailed.value = false
  } else {
    facetsFailed.value = true
    logger.warn('audit_facets_failed', { status: response.response?.status })
  }
}
watch(facetsQuery, (q) => void loadFacets(q), { immediate: true })

/* ---- table rows: cursor-stack paging, same contract as the findings grid ---- */
// filters or globals changed → any held cursor belongs to the old query: back to page 0
watch(facetsQuery, (q, old) => {
  if (old && JSON.stringify(q) !== JSON.stringify(old)) grid.resetPaging()
})

const rowsQuery = computed(() => {
  if (!clusterStore.selectedId) return null
  const q = buildFilterQuery(AUDIT_FIELDS, filters.selections, withGlobals())
  return { ...q, size: grid.size, ...(grid.activeCursor ? { cursor: grid.activeCursor } : {}) }
})

async function loadRows(q: typeof rowsQuery.value) {
  if (!q) return
  grid.loading = true
  const response = await readAuditLogApiV1AuditGet({
    query: q as ReadAuditLogApiV1AuditGetData['query'],
  })
  grid.loading = false
  if (response.response?.ok && response.data) {
    const body = response.data as unknown as {
      data: AuditEvent[]
      total: { value: number; relation: string }
      next_cursor: string | null
    }
    grid.setResult(body.data, body.total, body.next_cursor)
    grid.failed = false
  } else if (grid.page > 0) {
    // stale PIT cursor (410) is the usual culprit — rebuild the walk from page 0
    logger.warn('audit_page_failed_reset', { status: response.response?.status })
    grid.resetPaging()
  } else {
    grid.failed = true
    logger.warn('audit_load_failed', { status: response.response?.status })
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

/* ---- URL sync (M9a); global t/win keys are the shell's — preserve, never wipe ---- */
watch(
  () => filters.toQuery(),
  (q) => {
    void router.replace({ query: { ...keepTT(route.query), ...q } })
  },
)
watch(
  () => route.query,
  (q) => {
    if (JSON.stringify(filters.toQuery()) !== JSON.stringify(stripTT(q))) filters.fromQuery(q)
  },
)

/* ---- click-through (A-5): the row's decoration carries the finding's identity ---- */
function openFinding(row: AuditEvent) {
  const f = row.finding
  if (!f) return
  logger.debug('audit_row_clicked', { finding_key: row.entity_id })
  void router.push({
    name: 'finding',
    params: { cveId: f.cve_id },
    query: {
      digest: String(f.image_digest ?? ''),
      scanner: f.scanner ?? '',
      pkg: f.package_name ?? '',
    },
  })
}

const totalLabel = computed(
  () => `${grid.total.toLocaleString('en-US')}${grid.totalIsLowerBound ? '+' : ''}`,
)

/* ---- Export CSV (prototype screen-head action): fetch → blob → download, so a 413/failed
 * response surfaces as a message, not a broken tab (the ExportDialog pattern) ---- */
const toast = useToastStore()
const exporting = ref(false)

async function exportCsv() {
  const q = facetsQuery.value
  if (!q || exporting.value) return
  exporting.value = true
  const qs = new URLSearchParams(
    Object.entries(q).flatMap(([k, v]) =>
      v === undefined || v === null ? [] : [[k, String(v)] as [string, string]],
    ),
  )
  const resp = await fetch(`/api/v1/audit/export.csv?${qs}`, { credentials: 'same-origin' })
  exporting.value = false
  if (resp.status === 413) {
    toast.info('Over the inline export cap — narrow the filters first.')
    return
  }
  if (!resp.ok) {
    toast.error(`Export failed (${resp.status}) — check the backend connection.`)
    logger.warn('audit_export_failed', { status: resp.status })
    return
  }
  const blob = await resp.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `javv-audit-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
  toast.success(`Export downloaded · ${a.download}`)
}
</script>

<template>
  <div class="screen">
    <div class="screen-head screen-head-band">
      <div class="head-card">
        <h1>Audit log</h1>
        <p class="head-stat">
          {{ totalLabel }}<span class="head-unit"> events</span>
        </p>
        <p class="head-note">immutable, per user · window bounded by audit-log retention</p>
      </div>
      <AuditLens :query="facetsQuery" />
    </div>

    <div class="findings-layout">
      <div class="rail-col">
        <FacetRail
          :fields="AUDIT_FIELDS"
          :selections="filters.selections"
          :facets="facets"
          @toggle="filters.toggle"
        />
      </div>

      <div class="findings-main">
        <div class="toolbar-row">
          <FilterBar
            :fields="AUDIT_FIELDS"
            :selections="filters.selections"
            :facets="facets"
            @toggle="filters.toggle"
            @set-text="filters.setText"
            @clear-field="filters.clearField"
            @clear-all="filters.clearAll"
          />
          <UiButton variant="ghost" :disabled="exporting" @click="exportCsv">
            <AppIcon name="download" :size="14" />{{ exporting ? 'Exporting…' : 'Export CSV' }}
          </UiButton>
        </div>

        <p v-if="grid.failed || facetsFailed" class="load-error" role="alert">
          Audit log unavailable. Check the backend connection, then retry.
        </p>

        <AuditTable
          :rows="grid.rows"
          :loading="grid.loading"
          :filtered="filters.hasFilters"
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
/* head/layout/toolbar scaffolding lives in base.css (shared data-screen grammar) */
.load-error {
  margin: 0 0 10px;
}
</style>
