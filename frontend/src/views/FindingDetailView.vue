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
import { RouterLink, useRoute, useRouter } from 'vue-router'

import {
  readAuditLogApiV1AuditGet,
  listDecisionsApiV1DecisionsGet,
  revokeApiV1DecisionsDecisionIdRevokePost,
  searchFindingsApiV1FindingsGet,
  triageApiV1FindingsFindingKeyTriagePatch,
} from '@/api/generated'
import type { SearchFindingsApiV1FindingsGetData } from '@/api/generated'
import DisagreementBadge from '@/components/chips/DisagreementBadge.vue'
import EpssBar from '@/components/chips/EpssBar.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import SevChip from '@/components/chips/SevChip.vue'
import StateTag from '@/components/chips/StateTag.vue'
import DecisionsCard, { type DecisionRow } from '@/components/triage/DecisionsCard.vue'
import RiskAcceptDialog from '@/components/triage/RiskAcceptDialog.vue'
import TriagePanel from '@/components/triage/TriagePanel.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { useApi } from '@/composables/useApi'
import {
  affectedComponentRows,
  epssOf,
  kevOn,
  primaryRow,
  SCANNER_ORDER,
  scopeToPackage,
  severityDisagrees,
  type AffectedComponentRow,
} from '@/findings/detailViewModel'
import type { TriagePatchBody } from '@/findings/triageRules'
import { logger } from '@/lib/logger'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import type { FindingRow } from '@/stores/findings'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'

const route = useRoute()
const router = useRouter()
const clusterStore = useClusterStore()
const auth = useAuthStore()
const timeTravel = useTimeTravelStore()
const toast = useToastStore()
const { withGlobals } = useApi()

const cveId = computed(() => String(route.params.cveId ?? ''))
const digest = computed(() => (typeof route.query.digest === 'string' ? route.query.digest : null))
const clickedScanner = computed(() =>
  typeof route.query.scanner === 'string' ? route.query.scanner : null,
)

const rows = ref<FindingRow[]>([])
const affected = ref<AffectedComponentRow[]>([])
const affectedTruncated = ref(false)
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

/* ---- affected components: every occurrence of the CVE, server-side filtered; namespaces
        and versions ride per row (prototype "across what's actually running") ---- */
const occQuery = computed(() =>
  clusterStore.selectedId && cveId.value
    ? withGlobals({ cve_id: cveId.value, size: 200 })
    : null,
)

watch(
  occQuery,
  async (q, old) => {
    if (!q || JSON.stringify(q) === JSON.stringify(old)) return
    const response = await searchFindingsApiV1FindingsGet({
      query: q as SearchFindingsApiV1FindingsGetData['query'],
    })
    if (response.response?.ok && response.data) {
      const body = response.data as { data: FindingRow[]; total: number }
      affected.value = affectedComponentRows(body.data)
      affectedTruncated.value = body.total > body.data.length
    } else {
      logger.warn('finding_occurrences_failed', { status: response.response?.status })
    }
  },
  { immediate: true },
)

/* ---- view-model: everything reads the PACKAGE-scoped set (one row per scanner) ---- */
const pkg = computed(() => (typeof route.query.pkg === 'string' ? route.query.pkg : null))
const ver = computed(() =>
  typeof route.query.ver === 'string' && route.query.ver ? route.query.ver : null,
)
const scope = computed(() => scopeToPackage(rows.value, pkg.value, ver.value))
const evidence = computed(() => scope.value.scoped)
const otherPackages = computed(() => scope.value.otherPackages)
const primary = computed(() => primaryRow(evidence.value, clickedScanner.value))
const kev = computed(() => kevOn(evidence.value))
const epss = computed(() => epssOf(evidence.value))
const disagrees = computed(() => severityDisagrees(evidence.value))
const missingScanners = computed(() =>
  SCANNER_ORDER.filter((s) => !evidence.value.some((r) => r.scanner === s)),
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
const slaTier = computed(() => {
  if (primary.value?.overdue === true) return 'risk-num-over'
  const d = slaDaysLeft.value
  return d !== null && d <= 3 ? 'risk-num-tight' : ''
})
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

/* ---- triage (FR-7): the panel validates, this owns the PATCH + conflict surfacing ---- */
const saving = ref(false)
const triageError = ref<string | null>(null)
const historical = computed(() => timeTravel.t !== null)

async function saveTriage(body: TriagePatchBody) {
  const key = primary.value?.finding_key
  if (!key) return
  saving.value = true
  triageError.value = null
  const response = await triageApiV1FindingsFindingKeyTriagePatch({
    path: { finding_key: key },
    body,
  })
  saving.value = false
  if (response.response?.ok && response.data) {
    const updated = (response.data as { finding: FindingRow }).finding
    rows.value = rows.value.map((r) => (r.finding_key === key ? { ...r, ...updated } : r))
    logger.info('triage_saved', { finding_key: key, state: updated.state })
    toast.success('Triage saved')
  } else if (response.response?.status === 409) {
    triageError.value = 'Changed by someone else — reload and retry.'
  } else if (response.response?.status === 422) {
    triageError.value = 'The server rejected this transition — reload and retry.'
    logger.warn('triage_rejected', { status: 422 })
  } else {
    triageError.value = 'Save failed — check the backend connection.'
    logger.warn('triage_failed', { status: response.response?.status })
  }
}

/* ---- decisions on this CVE (immutable; revoked stay struck-through) ---- */
const raOpen = ref(false)
const decisions = ref<DecisionRow[]>([])
const decisionsBusy = ref(false)

async function fetchDecisions() {
  if (!clusterStore.selectedId || !cveId.value) return
  const response = await listDecisionsApiV1DecisionsGet({
    query: {
      cluster_id: clusterStore.selectedId,
      cve_id: cveId.value,
      include_revoked: true,
    },
  })
  if (response.response?.ok && response.data) {
    decisions.value = (response.data as { decisions: DecisionRow[] }).decisions ?? []
  } else {
    logger.warn('decisions_list_failed', { status: response.response?.status })
  }
}
watch([cveId, () => clusterStore.selectedId], () => void fetchDecisions(), { immediate: true })

async function revokeDecision(id: string) {
  decisionsBusy.value = true
  const response = await revokeApiV1DecisionsDecisionIdRevokePost({ path: { decision_id: id } })
  decisionsBusy.value = false
  if (response.response?.ok) {
    logger.info('decision_revoked', { decision_id: id })
    toast.success('Decision revoked')
    await fetchDecisions()
    void fetchActivity()
  } else {
    logger.warn('decision_revoke_failed', { status: response.response?.status })
  }
}

function onDecisionCreated() {
  toast.success('Decision recorded')
  void fetchDecisions()
  void fetchActivity()
}

/* ---- per-finding activity (the audit trail rows for THIS finding_key) ---- */
interface ActivityRow {
  event_id: string
  action: string
  actor: string
  field?: string
  old_value?: string | null
  new_value?: string | null
  '@timestamp': string
}
const activity = ref<ActivityRow[]>([])

async function fetchActivity() {
  const p = primary.value
  if (!p || !clusterStore.selectedId) return
  const response = await readAuditLogApiV1AuditGet({
    query: {
      cluster_id: clusterStore.selectedId,
      finding_key: p.finding_key,
      size: 8,
    } as never,
  })
  if (response.response?.ok && response.data) {
    activity.value = (response.data as { data: ActivityRow[] }).data
  } else {
    logger.warn('finding_activity_failed', { status: response.response?.status })
  }
}
watch([primary, () => clusterStore.selectedId], () => void fetchActivity(), { immediate: true })
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
      Finding unavailable. Check the backend connection.
    </p>

    <div v-else-if="!digest" class="not-found">
      <h1 class="mono">{{ cveId }}</h1>
      <p>This link is missing the image identity. Open the finding from the grid.</p>
    </div>

    <div v-else-if="rows.length === 0" class="not-found">
      <h1 class="mono">{{ cveId }}</h1>
      <p>
        No current finding for this CVE on this image. It may have been resolved by a newer
        scan, or the selected range ends before it was first seen.
      </p>
    </div>

    <template v-else>
      <div class="detail-head">
        <div class="detail-head-main">
          <div class="detail-cve">
            <h1>{{ cveId }}</h1>
            <SevChip v-if="primary" :level="primary.severity_canonical" />
            <DisagreementBadge v-if="disagrees" title="Scanners disagree on severity" />
            <span v-if="kev" class="kev-lg">KEV · known-exploited</span>
          </div>
          <div class="detail-meta">
            <div class="fact">
              <em>Package</em>
              <span class="fact-val mono-cell">{{ primary?.package_name }}</span>
            </div>
            <div class="fact">
              <em>Image</em>
              <RouterLink
                v-if="digest && primary?.image_repo"
                class="fact-val mono-cell fact-link"
                :to="{
                  path: `/images/${digest}`,
                  query: { repo: primary.image_repo, ...(primary.tag ? { tag: primary.tag } : {}) },
                }"
                title="Open this image's detail"
                >{{ primary.image_repo }}{{ primary.tag ? ':' + primary.tag : ''
                }}<AppIcon class="fact-go" name="chevron" :size="11"
              /></RouterLink>
              <span v-else class="fact-val mono-cell">{{ primary?.image_repo }}{{ primary?.tag ? ':' + primary.tag : '' }}</span>
            </div>
            <div class="fact">
              <em>First seen</em>
              <span class="fact-val">{{ fmtAt(primary?.first_seen_at) }}</span>
            </div>
            <div class="fact">
              <em>Last seen</em>
              <span class="fact-val">{{ fmtAt(primary?.last_seen_at) }}</span>
            </div>
          </div>
        </div>
        <div class="risk-band">
          <div class="risk-cell">
            <span class="risk-label">CVSS</span>
            <span class="risk-num" :class="`risk-num-${primary?.severity_canonical}`">{{ num(primary?.cvss) }}</span>
            <span class="risk-sub">via {{ primary?.scanner }}</span>
          </div>
          <div class="risk-cell">
            <span class="risk-label">EPSS</span>
            <span class="risk-num">{{ epss ? Math.round(epss.value * 100) + '%' : '—' }}</span>
            <span class="risk-sub">{{ epss ? `via ${epss.scanner}` : 'not scored' }}</span>
          </div>
          <div class="risk-cell">
            <span class="risk-label">SLA</span>
            <template v-if="primary?.due_at">
              <span class="risk-num" :class="slaTier">{{ slaDaysLeft }}<em>d</em></span>
              <span class="risk-sub">{{ primary.overdue ? 'Overdue' : 'by' }} {{ fmtAt(primary.due_at) }}</span>
            </template>
            <template v-else>
              <span class="risk-num risk-num-quiet">—</span>
              <span class="risk-sub">{{
                ['resolved', 'not_affected', 'risk_accepted'].includes(primary?.state ?? '')
                  ? `no deadline · ${primary?.state === 'not_affected' ? 'not affected' : primary?.state === 'risk_accepted' ? 'risk accepted' : 'resolved'}`
                  : 'no deadline'
              }}</span>
            </template>
          </div>
        </div>
      </div>

      <div class="detail-grid">
      <div class="detail-stack">
        <section class="card">
          <div class="card-head">
            <div>
              <h3>Per-scanner evidence</h3>
              <p class="card-sub">raw results, no black box</p>
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
              <AppIcon name="alert" :size="12" /> The scanners disagree. Both verdicts shown
              verbatim; JAVV never picks a winner.
            </p>
            <p v-else class="evidence-note">
              Scanners agree on severity. Dashboards facet by scanner so this finding is never
              double-counted.
            </p>
            <p v-if="otherPackages.length" class="evidence-note">
              This CVE also affects
              <span class="mono-cell sm">{{ otherPackages.slice(0, 5).join(', ') }}</span><template v-if="otherPackages.length > 5"> +{{ otherPackages.length - 5 }} more</template> on this image;
              open those rows from the grid.
            </p>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <div>
              <h3>Affected components <span class="count-badge">{{ affected.length }}{{ affectedTruncated ? '+' : '' }}</span></h3>
              <p class="card-sub">across the last committed inventory · one row per image + package, scanners listed, never merged</p>
            </div>
          </div>
          <div class="card-body">
            <div class="img-scroll">
            <table class="dtbl dtbl-bordered">
              <thead>
                <tr><th>Image</th><th>Namespace</th><th>Package</th><th>Current</th><th>Fixed</th><th>Scanners</th></tr>
              </thead>
              <tbody>
                <tr v-if="affected.length === 0"><td colspan="6" class="empty-row">No occurrences returned.</td></tr>
                <tr v-for="a in affected" :key="`${a.image}|${a.packageName}|${a.current}|${a.fixed}`">
                  <td class="mono-cell strong">{{ a.image }}</td>
                  <td class="mono-cell sm">{{ a.namespaces.join(', ') || '—' }}</td>
                  <td class="mono-cell sm">{{ a.packageName }}</td>
                  <td class="mono-cell sm">{{ a.current ?? '—' }}</td>
                  <td class="mono-cell sm" :class="{ 'no-fix': !a.fixed }">{{ a.fixed ?? 'no fix' }}</td>
                  <td><ScannerTag v-for="s in a.scanners" :key="s" :name="s" class="scn-gap" /></td>
                </tr>
              </tbody>
            </table>
            </div>
            <p v-if="affectedTruncated" class="evidence-note">
              Showing the first {{ affected.length }} components — more exist. Narrow via the
              Findings grid (search the CVE id).
            </p>
            <p class="evidence-note">
              A package listed by one scanner only, or twice with different versions, is a scanner
              disagreement — not a clean bill. Workload names land with the envelope (v1.1).
            </p>
          </div>
        </section>
      </div>

      <TriagePanel
        v-if="primary"
        :finding="primary"
        :can-triage="auth.hasCapability('can_triage')"
        :can-accept-final="auth.hasCapability('can_accept_audit_final')"
        :historical="historical"
        :saving="saving"
        :error="triageError"
        :current-user="auth.user?.username ?? null"
        @save="saveTriage"
        @risk-accept="raOpen = true"
      />
      </div>

      <DecisionsCard
        :decisions="decisions"
        :can-accept-final="auth.hasCapability('can_accept_audit_final')"
        :busy="decisionsBusy"
        @create="raOpen = true"
        @revoke="revokeDecision"
      />

      <section class="card activity-card">
        <div class="card-head">
          <div>
            <h3>Activity on this finding</h3>
            <p class="card-sub">the audit trail — every triage action, who &amp; when</p>
          </div>
        </div>
        <div class="card-body">
          <p v-if="activity.length === 0" class="empty-row">No triage actions yet.</p>
          <ul v-else class="act-list">
            <li v-for="a in activity" :key="a.event_id" class="act-row">
              <span class="act-when mono-cell">{{ fmtAt(a['@timestamp']) }}</span>
              <span class="act-what">
                <b>{{ a.actor }}</b> · {{ a.action }}
                <template v-if="a.field === 'state' && a.new_value">
                  — <StateTag :state="a.new_value" />
                </template>
                <template v-else-if="a.new_value">
                  — {{ a.field }}: <span class="mono-cell sm">{{ a.new_value }}</span>
                </template>
              </span>
            </li>
          </ul>
          <p v-if="activity.length >= 8" class="cap-note">Latest 8 actions. The full trail lives on the Audit screen (M9d).</p>
        </div>
      </section>

      <RiskAcceptDialog
        v-if="raOpen && primary"
        :cve-id="cveId"
        :finding="primary"
        @close="raOpen = false"
        @created="onDecisionCreated"
      />
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
  cursor: default;
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
  align-items: flex-start;
  gap: 14px 28px;
  margin-top: 18px;
}
.fact {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.detail-meta em {
  font-style: normal;
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--soft);
}
.fact-val {
  font-size: var(--text-body);
  color: var(--ink);
}
.fact-link {
  text-decoration: none;
  transition: color var(--dur-quick);
}
.fact-link:hover {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.fact-link:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.fact-go {
  color: var(--dash-muted);
  margin-left: 3px;
  vertical-align: -1px;
}
.fact-link:hover .fact-go {
  color: var(--coral-text);
}
.fact-num {
  font-size: var(--text-kpi);
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.meta-src {
  font-style: normal;
  color: var(--soft);
  font-size: var(--text-sm);
  font-weight: 400;
  letter-spacing: 0;
}
/* the risk band: one joined card, hairline-divided cells, urgency carried by the numerals
   (stat-card grammar per the operator's Nuxt UI reference — ours, on tokens) */
.risk-band {
  flex: none;
  display: flex;
  align-items: stretch;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--card);
}
.risk-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 20px;
  min-width: 104px;
}
.risk-cell + .risk-cell {
  border-left: 1px solid var(--line2);
}
.risk-label {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--soft);
}
.risk-num {
  font-size: var(--text-kpi);
  font-weight: 600;
  letter-spacing: -0.03em;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
  line-height: 1.15;
}
.risk-num em {
  font-style: normal;
  font-size: var(--text-body);
  color: var(--soft);
}
.risk-num-critical,
.risk-num-over {
  color: var(--sev-critical-fg);
}
.risk-num-high,
.risk-num-tight {
  color: var(--sla-tight-fg);
}
.risk-num-quiet {
  color: var(--soft);
  font-weight: 400;
}
.risk-sub {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink);
  margin-top: 2px;
  max-width: 170px;
}

.detail-grid {
  display: grid;
  grid-template-columns: 1.55fr 1fr;
  gap: var(--space-4);
  align-items: start;
  margin-top: var(--space-6); /* the header is its own band — give it air below */
}
@media (max-width: 1180px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
.detail-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
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
.count-badge {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 400;
  color: var(--soft);
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-chip);
  padding: 2px 7px;
  margin-left: 6px;
  vertical-align: 2px;
}
/* 100+ images must not become a wall — the table scrolls inside its viewport (≈9 rows) */
.img-scroll {
  max-height: 340px;
  overflow-y: auto;
}
.img-scroll thead th {
  position: sticky;
  top: 0;
  background: var(--card);
  z-index: 1;
}
.no-fix {
  color: var(--soft);
  font-style: italic;
}
.scn-gap {
  margin-right: 4px;
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

.activity-card {
  margin-top: var(--space-4); /* belongs to the decisions band — tighter than a new band */
}
.cap-note {
  margin: 10px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.act-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.act-row {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: var(--text-body);
}
.act-when {
  flex: none;
  font-size: var(--text-sm);
  color: var(--soft);
  min-width: 92px;
}
.act-what {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ink);
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
