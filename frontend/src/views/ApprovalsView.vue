<script setup lang="ts">
/**
 * Approvals (M9d slice 4, bolt #38) — the accept-final holder's REVIEW QUEUE over standing
 * risk-acceptances (ruling #30: creation is already SEC-2-gated, so this is not a pending-
 * approval workflow; revoked decisions never appear here). Wire: GET /decisions/approvals —
 * active risk-accepts, soonest-expiring first, server offset paging. The five slice rulings
 * (operator, 2026-07-13): no facet rail v1 · decision-activity lens · row → CVE-searched
 * findings · T<now = limitation notice (the endpoint has no as_of seam) · expiry-warn knob.
 * Route + nav are capability-gated (can_accept_audit_final) since the M9a shell.
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { approvalListApiV1DecisionsApprovalsGet, revokeApiV1DecisionsDecisionIdRevokePost } from '@/api/generated'
import { scannerLabel, scopeLabel, type ApprovalRow } from '@/approvals/viewModel'
import EditDecisionDialog from '@/components/approvals/EditDecisionDialog.vue'
import ExpiryChip from '@/components/chips/ExpiryChip.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import AuditLens from '@/components/dashboards/AuditLens.vue'
import LimitedHistoricalNotice from '@/components/dashboards/LimitedHistoricalNotice.vue'
import GridPager from '@/components/findings/GridPager.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'
import { refNowMs } from '@/system/clock'
import { lastDataAt } from '@/system/freshness'

const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const toast = useToastStore()
const router = useRouter()

const rows = ref<ApprovalRow[]>([])
const total = ref(0)
const page = ref(0)
const size = ref(25)
const settled = ref(false)
const failed = ref(false)

/** countdowns measure from the display clock (D28) — wall time at now, T when rewound */
const nowMs = computed(() => refNowMs(timeTravel.t))

async function fetchQueue() {
  if (!clusterStore.selectedId || !timeTravel.isNow) return
  const response = await approvalListApiV1DecisionsApprovalsGet({
    query: { cluster_id: clusterStore.selectedId, size: size.value, offset: page.value * size.value },
  })
  failed.value = !response.response?.ok
  if (!failed.value && response.data) {
    const data = response.data as { approvals: ApprovalRow[]; total: number }
    rows.value = data.approvals
    total.value = data.total
  } else {
    logger.warn('approvals_fetch_failed', { status: response.response?.status })
    rows.value = []
  }
  settled.value = true
}
watch(
  [() => clusterStore.selectedId, () => timeTravel.isNow, page, size],
  ([cid], old) => {
    if (old && old[0] !== cid) {
      settled.value = false
      page.value = 0
    }
    void fetchQueue()
  },
  { immediate: true },
)

/* the decision-activity lens (ruling 2): the journal sliced to entity_type=decision —
   create + revoke are the only decision actions, so one term is the exact slice */
const lensQuery = computed(() =>
  clusterStore.selectedId
    ? { cluster_id: clusterStore.selectedId, entity_type: 'decision', ...timeTravel.asOfParams }
    : null,
)

/* row click (ruling 3): the findings grid searched to the CVE — a decision may be
   cluster-wide, so the grid (not a single finding) is the honest landing */
function openFindings(row: ApprovalRow) {
  logger.debug('approval_row_clicked', { decision_id: row.decision_id })
  const query: Record<string, string> = { q: row.cve_id }
  if (row.scope.images.length === 1) query.image = row.scope.images[0] as string
  void router.push({ name: 'findings', query })
}

/* ---- actions: revoke (confirm-in-row) + edit (revoke+new dialog) ---- */
const confirmRevoke = ref<string | null>(null) // decision_id awaiting the second click
const busy = ref(false)
const editing = ref<ApprovalRow | null>(null)

async function revoke(row: ApprovalRow) {
  if (confirmRevoke.value !== row.decision_id) {
    confirmRevoke.value = row.decision_id
    return
  }
  confirmRevoke.value = null
  busy.value = true
  const response = await revokeApiV1DecisionsDecisionIdRevokePost({
    path: { decision_id: row.decision_id },
  })
  busy.value = false
  if (response.response?.ok) {
    logger.info('decision_revoked', { decision_id: row.decision_id })
    toast.success('Acceptance revoked — its findings return to open on the next projection')
    await fetchQueue()
  } else {
    logger.warn('decision_revoke_failed', { status: response.response?.status })
    toast.error('Revoke failed — check the backend connection')
  }
}

function onEdited() {
  toast.success('Decision re-issued (revoke + new)')
  void fetchQueue()
}

const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <div class="screen">
    <div class="screen-head screen-head-band">
      <div class="head-card">
        <h1>Approvals</h1>
        <p class="head-stat">
          <template v-if="timeTravel.isNow">{{ fmt(total) }}</template
          ><template v-else>—</template
          ><span class="head-unit"> standing acceptance{{ total === 1 && timeTravel.isNow ? '' : 's' }}</span>
        </p>
        <p class="head-note">review queue · active risk-accepts, soonest expiry first · revoked never listed</p>
      </div>
      <AuditLens
        :query="lensQuery"
        title="Decision activity"
        sub="risk-accept creates + revokes journaled in this range — the queue below is current state"
      />
    </div>

    <LimitedHistoricalNotice
      v-if="!timeTravel.isNow"
      title="The approvals queue answers for now"
      body="Standing acceptances are current state — the endpoint has no historical seam yet.
        The decision-activity lens above still rewinds; return to now to review the queue."
    />

    <template v-else>
      <div v-if="!settled" class="skel skel-table" aria-busy="true" aria-label="Loading approvals" />
      <p v-else-if="failed" class="load-error" role="alert">
        Could not load the queue — check the backend connection.
      </p>
      <section v-else class="card queue-card">
        <table class="tbl tbl-hover">
          <thead>
            <tr>
              <th>CVE</th>
              <th>Scope</th>
              <th>Scanner</th>
              <th>Justification</th>
              <th>Approver</th>
              <th class="fit">Expires</th>
              <th class="fit">Status</th>
              <th class="fit">Created</th>
              <th class="fit"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.decision_id" @click="openFindings(row)">
              <td><span class="mono-cell strong nowrap cve-link">{{ row.cve_id }}</span></td>
              <td>
                <span class="scope-cell" :class="{ 'scope-wide': scopeLabel(row.scope) === 'cluster-wide' }">
                  {{ scopeLabel(row.scope) }}
                </span>
              </td>
              <td>
                <ScannerTag v-if="!row.apply_both_scanners && row.scanner" :name="row.scanner" />
                <span v-else class="both-tag">{{ scannerLabel(row) }}</span>
              </td>
              <td class="just-cell" :title="row.justification">{{ row.justification }}</td>
              <td class="sm">{{ row.created_by }}</td>
              <td class="fit">
                <span class="mono-cell sm nowrap" :title="row.expiry ?? 'no expiry set'">
                  {{ row.expiry ? lastDataAt(row.expiry) : '—' }}
                </span>
              </td>
              <td class="fit"><ExpiryChip :expiry="row.expiry" :now-ms="nowMs" /></td>
              <td class="fit">
                <span class="mono-cell sm nowrap" :title="row.created_at">{{ lastDataAt(row.created_at) }}</span>
              </td>
              <td class="fit row-actions" @click.stop>
                <UiButton variant="mini" :disabled="busy" @click="editing = row">Edit</UiButton>
                <UiButton
                  variant="mini"
                  :class="{ 'revoke-armed': confirmRevoke === row.decision_id }"
                  :disabled="busy"
                  @click="revoke(row)"
                >
                  {{ confirmRevoke === row.decision_id ? 'Confirm revoke' : 'Revoke' }}
                </UiButton>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="rows.length === 0" class="empty-row">
          No standing risk-acceptances — accepted findings land here for review.
        </div>
        <div class="queue-pager">
          <GridPager
            :total="total"
            :page="page"
            :size="size"
            :shown="rows.length"
            :has-prev="page > 0"
            :has-next="(page + 1) * size < total"
            @prev="page = Math.max(0, page - 1)"
            @next="page = page + 1"
            @update:size="(s) => { size = s; page = 0 }"
          />
        </div>
      </section>
    </template>

    <EditDecisionDialog
      v-if="editing"
      :decision="editing"
      @close="editing = null"
      @edited="onEdited"
    />
  </div>
</template>

<style scoped>
.queue-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
  margin-top: 16px;
}
.queue-card .tbl th:first-child,
.queue-card .tbl td:first-child {
  padding-left: 16px;
}
/* link affordance on the identifier, the findings-grid grammar */
.queue-card :deep(.cve-link) {
  transition: color 0.12s ease-out;
}
.queue-card .tbl-hover tbody tr:hover :deep(.cve-link) {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .queue-card :deep(.cve-link) {
    transition: none;
  }
}
.scope-cell {
  font-size: var(--text-sm);
}
.scope-wide {
  color: var(--soft);
  font-style: italic;
}
.both-tag {
  font-family: var(--font-mono);
  font-size: var(--text-chip-sm);
  color: var(--soft);
  background: var(--line2);
  padding: 2px 6px;
  border-radius: 4px;
}
.just-cell {
  max-width: 340px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-sm);
}
.row-actions {
  display: flex;
  gap: 6px;
  white-space: nowrap;
}
/* two-click revoke: the armed state speaks in the alarm register — hue in bg/border,
   prose stays ink (the ratchet's same-hue rule, DESIGN.md §2) */
.row-actions :deep(.revoke-armed) {
  background: var(--sev-critical-bg);
  border-color: var(--sev-critical-solid);
  color: var(--ink);
}
.skel-table {
  height: 220px;
  margin-top: 16px;
  border-radius: var(--r);
  background: linear-gradient(90deg, var(--line2) 25%, var(--panel) 50%, var(--line2) 75%);
  background-size: 200% 100%;
  animation: appr-shimmer 1.4s ease-in-out infinite;
}
@keyframes appr-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
@media (prefers-reduced-motion: reduce) {
  .skel-table {
    animation: none;
  }
}
/* the in-card pager wrapper — the LeaderboardTable reference (pager never sits flush) */
.queue-pager {
  padding: 0 12px 10px;
}
.queue-pager :deep(.pager) {
  margin-top: 6px;
}
.load-error {
  margin-top: 16px;
  color: var(--health-down-fg);
  font-size: var(--text-body);
}
</style>
