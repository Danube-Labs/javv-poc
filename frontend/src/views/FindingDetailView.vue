<script setup lang="ts">
/**
 * Finding detail (M9b slice 2, read-only — triage panel lands slice 3). Ported structure:
 * prototype screens-finding-detail.jsx `FindingDetail` (back-link → detail-head → evidence
 * stack), tokens win on palette. Identity = (cve_id, image_digest); the pair query carries NO
 * scanner filter — the returned rows ARE the per-scanner evidence table (A-3, never
 * reconciled). Header renders only real doc fields (B-2/B-3); SLA is the server's due_at/
 * overdue (B-5). Historical rows null fields out — everything here tolerates that.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  groupFindingsApiV1FindingsGroupsGet,
  searchFindingsApiV1FindingsGet,
} from '@/api/generated'
import type {
  GroupFindingsApiV1FindingsGroupsGetData,
  SearchFindingsApiV1FindingsGetData,
} from '@/api/generated'
import DisagreementBadge from '@/components/chips/DisagreementBadge.vue'
import EpssBar from '@/components/chips/EpssBar.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import SevChip from '@/components/chips/SevChip.vue'
import StateTag from '@/components/chips/StateTag.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { useApi } from '@/composables/useApi'
import {
  epssOf,
  imageGroupRows,
  kevOn,
  orderEvidence,
  primaryRow,
  SCANNER_ORDER,
  severityDisagrees,
  type ImageGroupRow,
} from '@/findings/detailViewModel'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import type { FindingRow } from '@/stores/findings'

const route = useRoute()
const router = useRouter()
const clusterStore = useClusterStore()
const { withGlobals } = useApi()

const cveId = computed(() => String(route.params.cveId ?? ''))
const digest = computed(() => (typeof route.query.digest === 'string' ? route.query.digest : null))
const clickedScanner = computed(() =>
  typeof route.query.scanner === 'string' ? route.query.scanner : null,
)

const rows = ref<FindingRow[]>([])
const groups = ref<ImageGroupRow[]>([])
const loading = ref(true)
const failed = ref(false)

/* ---- the sibling pair: one query, no scanner filter (A-3) ---- */
const pairQuery = computed(() =>
  clusterStore.selectedId && cveId.value && digest.value
    ? withGlobals({ cve_id: cveId.value, image_digest: digest.value, size: 10 })
    : null,
)

watch(
  pairQuery,
  async (q, old) => {
    if (!q || JSON.stringify(q) === JSON.stringify(old)) return
    loading.value = true
    const response = await searchFindingsApiV1FindingsGet({
      query: q as SearchFindingsApiV1FindingsGetData['query'],
    })
    loading.value = false
    if (response.response?.ok && response.data) {
      rows.value = (response.data as { data: FindingRow[] }).data
      failed.value = false
    } else {
      failed.value = true
      logger.warn('finding_detail_failed', { status: response.response?.status })
    }
  },
  { immediate: true },
)

/* ---- images affected: server aggregation, per-scanner counts (B-4) ---- */
const groupsQuery = computed(() =>
  clusterStore.selectedId && cveId.value
    ? withGlobals({ by: 'image_repo', cve_id: cveId.value, size: 50 })
    : null,
)

watch(
  groupsQuery,
  async (q, old) => {
    if (!q || JSON.stringify(q) === JSON.stringify(old)) return
    const response = await groupFindingsApiV1FindingsGroupsGet({
      query: q as GroupFindingsApiV1FindingsGroupsGetData['query'],
    })
    if (response.response?.ok && response.data) {
      const body = response.data as {
        data: { key: string; count: number; by_scanner: Record<string, number> }[]
      }
      groups.value = imageGroupRows(body.data)
    } else {
      logger.warn('finding_groups_failed', { status: response.response?.status })
    }
  },
  { immediate: true },
)

/* ---- view-model ---- */
const evidence = computed(() => orderEvidence(rows.value))
const primary = computed(() => primaryRow(rows.value, clickedScanner.value))
const kev = computed(() => kevOn(rows.value))
const epss = computed(() => epssOf(rows.value))
const disagrees = computed(() => severityDisagrees(rows.value))
const missingScanners = computed(() =>
  SCANNER_ORDER.filter((s) => !rows.value.some((r) => r.scanner === s)),
)

/* ---- display helpers (24h everywhere, null-tolerant) ---- */
function fmtAt(iso: unknown): string {
  if (typeof iso !== 'string') return '—'
  return new Date(iso).toLocaleString('en-GB', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}
const slaDaysLeft = computed(() => {
  const due = primary.value?.due_at
  if (typeof due !== 'string') return null
  // display-only countdown derived FROM the server deadline (B-5: the deadline itself is never client math)
  return Math.ceil((new Date(due).getTime() - Date.now()) / 86_400_000)
})
function num(v: unknown): string {
  return typeof v === 'number' ? String(v) : '—'
}
function verbatimDiffers(r: FindingRow): boolean {
  return r.severity.toLowerCase() !== r.severity_canonical
}

function goBack() {
  if (window.history.state?.back) router.back()
  else void router.push({ name: 'findings' })
}
</script>

<template>
  <div class="screen">
    <button class="back-link" @click="goBack"><AppIcon name="arrowback" :size="15" />Findings</button>

    <!-- loading: skeletons, not spinners -->
    <div v-if="loading" aria-busy="true" aria-label="Loading finding">
      <div class="skel skel-head" />
      <div class="skel skel-card" />
      <div class="skel skel-card" />
    </div>

    <p v-else-if="failed" class="load-error" role="alert">
      Finding unavailable — check the backend connection.
    </p>

    <div v-else-if="!digest" class="not-found">
      <h1 class="mono">{{ cveId }}</h1>
      <p>This link is missing the image identity — open the finding from the grid.</p>
    </div>

    <div v-else-if="rows.length === 0" class="not-found">
      <h1 class="mono">{{ cveId }}</h1>
      <p>
        No current finding for this CVE on this image — it may have been resolved by a newer
        scan, or the selected range ends before it was first seen.
      </p>
    </div>

    <template v-else>
      <div class="detail-head">
        <div class="detail-head-main">
          <div class="detail-cve">
            <h1>{{ cveId }}</h1>
            <SevChip v-if="primary" :level="primary.severity_canonical" solid />
            <DisagreementBadge v-if="disagrees" title="Scanners disagree on severity" />
            <span v-if="kev" class="kev-lg">KEV · known-exploited</span>
          </div>
          <div class="detail-meta">
            <span><em>CVSS</em> {{ num(primary?.cvss) }}</span>
            <span>
              <em>EPSS</em>
              <template v-if="epss">{{ Math.round(epss.value * 100) }}% <i class="meta-src">via {{ epss.scanner }}</i></template>
              <template v-else>—</template>
            </span>
            <span><em>Package</em> <span class="mono-cell">{{ primary?.package_name }}</span></span>
            <span><em>Image</em> <span class="mono-cell">{{ primary?.image_repo }}{{ primary?.tag ? ':' + primary.tag : '' }}</span></span>
            <span><em>First seen</em> {{ fmtAt(primary?.first_seen_at) }}</span>
            <span><em>Last seen</em> {{ fmtAt(primary?.last_seen_at) }}</span>
          </div>
        </div>
        <div class="sla-box" :class="{ 'sla-box-over': primary?.overdue === true }">
          <span class="sla-box-label">SLA</span>
          <template v-if="primary?.due_at">
            <span class="sla-box-days">{{ slaDaysLeft }}<em>d</em></span>
            <span class="sla-box-deadline">{{ primary.overdue ? 'Overdue' : 'by' }} {{ fmtAt(primary.due_at) }}</span>
          </template>
          <span v-else class="sla-box-deadline">no deadline</span>
        </div>
      </div>

      <div class="detail-stack">
        <section class="card">
          <div class="card-head">
            <div>
              <h3>Per-scanner evidence</h3>
              <p class="card-sub">raw results — no black box</p>
            </div>
            <span class="card-tag">no cross-scanner merge</span>
          </div>
          <div class="card-body">
            <table class="dtbl dtbl-bordered">
              <thead>
                <tr>
                  <th>Scanner</th><th>Severity</th><th>CVSS</th><th>Package</th><th>Fixed in</th>
                  <th>EPSS</th><th>State</th><th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in evidence" :key="r.finding_key">
                  <td><ScannerTag :name="r.scanner" /></td>
                  <td>
                    <SevChip :level="r.severity_canonical" />
                    <span v-if="verbatimDiffers(r)" class="mono-cell sm verbatim" :title="'verbatim from ' + r.scanner">“{{ r.severity }}”</span>
                  </td>
                  <td class="mono-cell sm">{{ num(r.cvss) }}</td>
                  <td class="mono-cell sm">{{ r.package_name }}</td>
                  <td>
                    <span v-if="r.fixed_version" class="mono-cell sm ver-fix">{{ r.fixed_version }}</span>
                    <span v-else class="ver-none">no fix</span>
                  </td>
                  <td><EpssBar :v="r.epss" /></td>
                  <td><StateTag :state="r.state" /></td>
                  <td class="mono-cell sm">{{ fmtAt(r.last_seen_at) }}</td>
                </tr>
                <tr v-for="s in missingScanners" :key="s" class="absent-row">
                  <td><ScannerTag :name="s" /></td>
                  <td colspan="7" class="absent-note">
                    no current finding from this scanner for this CVE on this image
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-if="disagrees" class="evidence-note evidence-warn">
              <AppIcon name="alert" :size="12" /> The scanners disagree — both verdicts shown
              verbatim; JAVV never picks a winner.
            </p>
            <p v-else class="evidence-note">
              Scanners agree on severity. Dashboards facet by scanner so this finding is never
              double-counted.
            </p>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <div>
              <h3>Images affected</h3>
              <p class="card-sub">per-scanner finding counts for {{ cveId }} — never summed</p>
            </div>
          </div>
          <div class="card-body">
            <table class="dtbl dtbl-bordered">
              <thead>
                <tr><th>Image</th><th class="r">Trivy</th><th class="r">Grype</th><th class="r">Δ</th><th></th></tr>
              </thead>
              <tbody>
                <tr v-if="groups.length === 0"><td colspan="5" class="empty-row">No image groups returned.</td></tr>
                <tr v-for="g in groups" :key="g.repo">
                  <td class="mono-cell strong">{{ g.repo }}</td>
                  <td class="r mono-cell sm" :class="{ 'count-zero': g.zeroVsNonzero && (g.trivy ?? 0) === 0 }">{{ g.trivy ?? 0 }}</td>
                  <td class="r mono-cell sm" :class="{ 'count-zero': g.zeroVsNonzero && (g.grype ?? 0) === 0 }">{{ g.grype ?? 0 }}</td>
                  <td class="r mono-cell sm">{{ g.delta }}</td>
                  <td class="c"><DisagreementBadge v-if="g.zeroVsNonzero" title="One scanner reports zero here — treat like a severity disagreement" /></td>
                </tr>
              </tbody>
            </table>
            <p class="evidence-note">
              A zero next to a non-zero is a scanner disagreement, not a clean bill.
              Per-image detail lands with M9c.
            </p>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* prototype .back-link / .detail-head / .sla-box / .tbl-bordered family, on tokens.
   Deviation from the prototype (recorded in the PR): the 4px severity side-stripe on
   .detail-head is dropped — side-stripe accents are a banned pattern; severity is carried
   by the solid chip in the title row instead. */
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  color: var(--soft);
  font-size: var(--text-sm);
  font-family: var(--font-ui);
  padding: 0 0 14px;
  cursor: pointer;
}
.back-link:hover {
  color: var(--coral-text);
}
.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  padding: 20px 22px;
  box-shadow: var(--shadow);
}
.detail-cve {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.detail-cve h1 {
  font-size: var(--text-detail-mono);
  font-family: var(--font-mono);
  letter-spacing: -0.01em;
  margin: 0;
}
.kev-lg {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--kev-fg);
  background: var(--kev-bg);
  padding: 4px 9px;
  border-radius: var(--r-chip);
}
.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 18px 22px;
  margin-top: 14px;
}
.detail-meta > span {
  font-size: var(--text-sm);
  color: var(--ink);
}
.detail-meta em {
  font-style: normal;
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--soft);
  margin-right: 6px;
}
.meta-src {
  font-style: normal;
  color: var(--soft);
}
.sla-box {
  flex: none;
  width: 128px;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: var(--panel);
}
.sla-box-over {
  background: var(--sev-critical-bg);
  border-color: var(--sev-critical-line);
}
.sla-box-label {
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--soft);
}
.sla-box-days {
  font-size: var(--text-kpi);
  font-weight: 600;
  letter-spacing: -0.03em;
  color: var(--ink);
}
.sla-box-days em {
  font-style: normal;
  font-size: var(--text-body);
  color: var(--soft);
}
.sla-box-deadline {
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  color: var(--soft);
  margin-top: 3px;
}
.sla-box-over .sla-box-days,
.sla-box-over .sla-box-deadline {
  color: var(--sev-critical-fg);
}

.detail-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 16px;
}
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--line2);
}
.card-head h3 {
  margin: 0;
}
.card-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.card-tag {
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  letter-spacing: 0.04em;
  color: var(--teal-text);
  background: var(--note-info-bg);
  padding: 4px 8px;
  border-radius: 6px;
  text-transform: uppercase;
  flex: none;
}
.card-body {
  padding: 14px 16px;
  overflow-x: auto;
}

.dtbl {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-mono-cell);
}
.dtbl th {
  text-align: left;
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--soft);
  font-weight: 400;
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
}
.dtbl td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--line2);
  vertical-align: middle;
}
.dtbl tr:last-child td {
  border-bottom: 0;
}
.dtbl-bordered td,
.dtbl-bordered th {
  border-right: 1px solid var(--line2);
}
.dtbl-bordered td:last-child,
.dtbl-bordered th:last-child {
  border-right: 0;
}
.dtbl .r {
  text-align: right;
}
.dtbl .c {
  text-align: center;
}
.dtbl .sm {
  font-size: var(--text-sm);
}
.mono-cell {
  font-family: var(--font-mono);
}
.strong {
  font-weight: 700;
}
.verbatim {
  margin-left: 8px;
  color: var(--soft);
}
.ver-fix {
  color: var(--teal-text);
}
.ver-none {
  color: var(--ver-none-fg);
  font-style: italic;
  font-size: var(--text-sm);
}
.count-zero {
  color: var(--coral-text);
  font-weight: 700;
}
.absent-row td {
  background: var(--panel);
}
.absent-note {
  color: var(--soft);
  font-size: var(--text-sm);
}
.empty-row {
  text-align: center;
  color: var(--soft);
  padding: 28px 12px;
}
.evidence-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 12px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.5;
}
.evidence-warn {
  color: var(--ink);
}
.evidence-warn svg {
  color: var(--sev-high-fg);
  flex: none;
}

.not-found h1 {
  font-family: var(--font-mono);
}
.not-found p {
  color: var(--soft);
  max-width: 62ch;
}
.load-error {
  color: var(--health-down-fg);
  font-size: var(--text-body);
}

/* skeletons (impeccable product register: skeletons over spinners) */
.skel {
  border-radius: var(--r);
  background: linear-gradient(90deg, var(--line2) 25%, var(--panel) 50%, var(--line2) 75%);
  background-size: 200% 100%;
  animation: skel-shimmer 1.4s ease-in-out infinite;
}
.skel-head {
  height: 112px;
}
.skel-card {
  height: 180px;
  margin-top: 16px;
}
@keyframes skel-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .skel {
    animation: none;
  }
}
</style>
