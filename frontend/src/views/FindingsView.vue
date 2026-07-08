<script setup lang="ts">
/**
 * Findings screen skeleton: the M9a filter module wired end-to-end — one FINDINGS_FIELDS config
 * driving FacetRail + FilterBar, selections URL-synced (shareable views), facet counts live from
 * `GET /api/v1/findings/facets` (cluster_id + as_of injected on every read). The grid itself
 * lands in M9b.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { facetFindingsApiV1FindingsFacetsGet } from '@/api/generated'
import type { FacetFindingsApiV1FindingsFacetsGetData } from '@/api/generated'
import FacetRail from '@/components/filters/FacetRail.vue'
import FilterBar from '@/components/filters/FilterBar.vue'
import { useApi } from '@/composables/useApi'
import { buildFilterQuery } from '@/filters/buildFilterQuery'
import type { FacetsResponse } from '@/filters/facets'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { logger } from '@/lib/logger'
import { makeFiltersStore } from '@/stores/filters'
import { useClusterStore } from '@/stores/cluster'
import { SEV_COLOR, type Severity } from '@/styles/tokens'

const useFindingsFilters = makeFiltersStore('findings-filters', FINDINGS_FIELDS)
const filters = useFindingsFilters()
const clusterStore = useClusterStore()
const { withGlobals } = useApi()
const route = useRoute()
const router = useRouter()

const facets = ref<FacetsResponse>({})
const loading = ref(false)
const failed = ref(false)

filters.fromQuery(route.query)

const query = computed(() =>
  clusterStore.selectedId ? buildFilterQuery(FINDINGS_FIELDS, filters.selections, withGlobals()) : null,
)

watch(
  query,
  async (q) => {
    if (!q) return
    loading.value = true
    const response = await facetFindingsApiV1FindingsFacetsGet({
      // builder output is a generic param record; the endpoint type is the precise contract
      query: q as FacetFindingsApiV1FindingsFacetsGetData['query'],
    })
    loading.value = false
    if (response.response?.ok && response.data) {
      facets.value = (response.data as { facets: FacetsResponse }).facets
      failed.value = false
    } else {
      failed.value = true
      logger.warn('findings_facets_failed', { status: response.response?.status })
    }
  },
  { immediate: true },
)

// selections → URL (replace, not push — filter churn shouldn't pollute history)
watch(
  () => filters.toQuery(),
  (q) => {
    void router.replace({ query: q })
  },
)
// URL → selections (back/forward, pasted links)
watch(
  () => route.query,
  (q) => {
    if (JSON.stringify(filters.toQuery()) !== JSON.stringify(q)) filters.fromQuery(q)
  },
)

const sevSolid = (value: string) => SEV_COLOR[value as Severity]?.solid
</script>

<template>
  <div class="screen">
    <div class="screen-head">
      <div>
        <h1>Findings</h1>
        <p class="screen-sub">kept per-scanner, no cross-merge</p>
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
          <span v-if="field.key === 'severity'" class="sev-dot" :style="{ background: sevSolid(value) }" />
          {{ label }}
        </template>
      </FacetRail>

      <div class="findings-main">
        <FilterBar
          :fields="FINDINGS_FIELDS"
          :selections="filters.selections"
          :facets="facets"
          @toggle="filters.toggle"
          @set-text="filters.setText"
          @clear-field="filters.clearField"
          @clear-all="filters.clearAll"
        />
        <section class="card grid-stub" role="status">
          <p v-if="failed">Facets unavailable — check the backend connection.</p>
          <p v-else-if="loading">Loading facet counts…</p>
          <p v-else>The findings grid lands with <span class="mono">M9b</span> — filters above and to the left are live.</p>
        </section>
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
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 14px 16px;
}
.grid-stub {
  color: var(--soft);
  font-size: var(--text-body);
}
.sev-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
}
</style>
