<script setup lang="ts">
/**
 * Image detail — per-digest drill-down (M9c slice 3; SCREENS-v5 §8). Identity is the content
 * digest; `repo:tag` ride along as query context. The scanner lens is a READ lens: it swaps
 * which scanner's committed findings + facets are shown — never merges (per-scanner sacred).
 * Severity cards and rows come from the same server reads the Findings screen uses
 * (`image_digest` scoped), so the two screens can never disagree; `as_of` rides every query
 * (T<now = the M8b reader, as-scanned).
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import type {
  FacetFindingsApiV1FindingsFacetsGetData,
  SearchFindingsApiV1FindingsGetData,
} from '@/api/generated'
import { facetFindingsApiV1FindingsFacetsGet, searchFindingsApiV1FindingsGet } from '@/api/generated'
import FindingsTable from '@/components/findings/FindingsTable.vue'
import GridPager from '@/components/findings/GridPager.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import { useApi } from '@/composables/useApi'
import type { SortField, SortOrder } from '@/findings/buildFindingsQuery'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import type { FindingRow } from '@/stores/findings'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { CHART_SEV, type Severity } from '@/styles/tokens'

const CARD_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low']
const SCANNER_OPTS = [
  { value: 'trivy', label: 'trivy' },
  { value: 'grype', label: 'grype' },
] as const
/* image/affected-images are this screen's own context; scanner is fixed by the lens */
const HIDDEN_COLUMNS: ReadonlySet<string> = new Set(['image', 'images', 'scanner'])

const route = useRoute()
const router = useRouter()
const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const { withGlobals } = useApi()

const digest = computed(() => String(route.params.digest ?? ''))
const repo = computed(() => (route.query.repo ? String(route.query.repo) : null))
const tag = computed(() => (route.query.tag ? String(route.query.tag) : null))
const title = computed(() =>
  repo.value ? `${repo.value.split('/').at(-1)}${tag.value ? `:${tag.value}` : ''}` : 'Image',
)

const scanner = ref<'trivy' | 'grype'>('trivy')

/* ---- severity cards: the lens scanner's facet buckets, image-scoped ---- */
const facets = ref<Record<string, { key: string; count: number }[]>>({})
const facetsFailed = ref(false)

/* ---- rows: cursor-stack paging local to this screen (one query family) ---- */
const rows = ref<FindingRow[]>([])
const total = ref(0)
const loading = ref(false)
const failed = ref(false)
const sort = ref<SortField>('severity_rank')
const order = ref<SortOrder>('desc')
const size = ref(25)
const page = ref(0)
const cursors = ref<(string | null)[]>([null]) // cursor that FETCHES page i
const nextCursor = ref<string | null>(null)

const baseQuery = computed(() =>
  clusterStore.selectedId
    ? withGlobals({
        cluster_id: clusterStore.selectedId,
        image_digest: digest.value,
        scanner: scanner.value,
      })
    : null,
)

async function loadFacets() {
  if (!baseQuery.value) return
  const { data, response } = await facetFindingsApiV1FindingsFacetsGet({
    query: baseQuery.value as FacetFindingsApiV1FindingsFacetsGetData['query'],
  })
  if (response?.ok && data) {
    facets.value = (data as { facets: typeof facets.value }).facets ?? {}
    facetsFailed.value = false
  } else {
    facetsFailed.value = true
    logger.warn('image_detail_facets_failed', { status: response?.status })
  }
}

async function loadRows() {
  if (!baseQuery.value) return
  loading.value = true
  const { data, response } = await searchFindingsApiV1FindingsGet({
    query: {
      ...baseQuery.value,
      sort: sort.value,
      order: order.value,
      size: size.value,
      ...(cursors.value[page.value] ? { cursor: cursors.value[page.value] } : {}),
    } as SearchFindingsApiV1FindingsGetData['query'],
  })
  loading.value = false
  if (response?.ok && data) {
    const body = data as { data: FindingRow[]; total: { value: number }; next_cursor: string | null }
    rows.value = body.data
    total.value = body.total.value
    nextCursor.value = body.next_cursor
    failed.value = false
  } else {
    failed.value = true
    logger.warn('image_detail_rows_failed', { status: response?.status })
  }
}

function resetPaging() {
  page.value = 0
  cursors.value = [null]
  nextCursor.value = null
}

watch(
  [baseQuery, sort, order, size],
  () => {
    resetPaging()
    void loadFacets()
    void loadRows()
  },
  { immediate: true },
)

function onSort(field: SortField) {
  if (sort.value === field) {
    order.value = order.value === 'desc' ? 'asc' : 'desc'
  } else {
    sort.value = field
    order.value = 'desc'
  }
}
function goNext() {
  if (!nextCursor.value) return
  cursors.value[page.value + 1] = nextCursor.value
  page.value += 1
  void loadRows()
}
function goPrev() {
  if (page.value === 0) return
  page.value -= 1
  void loadRows()
}

const sevCount = (s: Severity) => facets.value.severity?.find((b) => b.key === s)?.count ?? 0
const presentTotal = computed(() => facets.value.present?.find((b) => b.key === 'true')?.count ?? 0)

function openFinding(row: FindingRow) {
  logger.debug('image_finding_row_clicked', { finding_key: row.finding_key })
  void router.push({
    name: 'finding',
    params: { cveId: row.cve_id },
    query: { digest: digest.value, scanner: row.scanner, package: row.package_name ?? '' },
  })
}
const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <div class="screen">
    <div class="screen-head">
      <div>
        <UiButton variant="quiet" class="back-btn" @click="router.push('/images')">
          <AppIcon name="arrowback" :size="13" /> Running images
        </UiButton>
        <h1>{{ title }}</h1>
        <p class="screen-sub">
          <template v-if="repo"><span class="mono-cell">{{ repo }}{{ tag ? `:${tag}` : '' }}</span> · </template>
          <span class="mono-cell digest" :title="digest">{{ digest }}</span>
        </p>
      </div>
      <div class="head-actions">
        <span class="lens-label">Showing results from</span>
        <UiSegControl v-model="scanner" tone="neutral" :options="SCANNER_OPTS" />
      </div>
    </div>

    <p v-if="failed" class="load-error" role="alert">
      Image findings unavailable. Check the backend connection.
    </p>

    <template v-else>
      <!-- per-scanner severity cards: one scanner's buckets only — the lens swaps, never merges -->
      <div class="kpi-band sev-band">
        <div v-for="s in CARD_SEVERITIES" :key="s" class="kpi-cell kpi-static">
          <span class="kpi-label"><i class="kpi-dot" :style="{ background: CHART_SEV[s] }" />{{ s }}</span>
          <span class="kpi-num">{{ fmt(sevCount(s)) }}</span>
        </div>
        <div class="kpi-cell kpi-static">
          <span class="kpi-label"><i class="kpi-dot kpi-dot-total" />findings · {{ scanner }}</span>
          <span class="kpi-num">{{ fmt(presentTotal) }}</span>
        </div>
      </div>

      <section class="card grid-card">
        <div v-if="!loading && rows.length === 0" class="first-run">
          <h2>No findings from {{ scanner }}</h2>
          <p>
            {{ timeTravel.isNow
              ? `No committed ${scanner} findings for this digest — a clean scan or not scanned by ${scanner} yet.`
              : `As scanned at this T: no committed ${scanner} findings for this digest — clean then, or not yet scanned.` }}
          </p>
        </div>
        <template v-else>
          <FindingsTable
            :rows="rows"
            :sort="sort"
            :order="order"
            :loading="loading"
            :hidden="HIDDEN_COLUMNS"
            @sort="onSort"
            @row-click="openFinding"
          />
          <GridPager
            :total="total"
            :page="page"
            :size="size"
            :shown="rows.length"
            :has-prev="page > 0"
            :has-next="nextCursor !== null"
            @prev="goPrev"
            @next="goNext"
            @update:size="(s: number) => (size = s)"
          />
        </template>
      </section>
    </template>
  </div>
</template>

<style scoped>
.screen-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.back-btn {
  margin-bottom: 8px;
}
.screen-head h1 {
  margin: 0 0 4px;
}
.screen-sub {
  margin: 0;
  color: var(--soft);
  font-size: var(--text-body);
}
.digest {
  display: inline-block;
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.lens-label {
  font-size: var(--text-sm);
  color: var(--soft);
}

/* joined stat band — read-only cards (the ruled Nuxt grammar) */
.kpi-band {
  display: grid;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.sev-band {
  grid-template-columns: repeat(5, 1fr);
}
.kpi-cell {
  cursor: default;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 14px 16px 12px;
  border: none;
  background: var(--card);
  text-align: left;
}
.kpi-cell + .kpi-cell {
  border-left: 1px solid var(--line2);
}
.kpi-label {
  display: flex;
  align-items: center;
  gap: 7px;
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--soft);
  font-weight: 700;
}
.kpi-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.kpi-dot-total {
  background: var(--slate);
}
.kpi-num {
  font-size: var(--text-kpi);
  font-weight: 600;
  letter-spacing: -0.03em;
  line-height: 1.05;
  margin-top: 6px;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}

.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  margin-top: 16px;
}
.grid-card {
  overflow: hidden;
  padding: 0 0 4px;
}

.load-error {
  color: var(--health-down-fg);
  font-size: var(--text-body);
}
.first-run {
  padding: 48px 16px;
  text-align: center;
  color: var(--soft);
}
.first-run h2 {
  color: var(--ink);
  margin: 0 0 6px;
}
</style>
