<script setup lang="ts">
/**
 * "Decisions on this CVE" (prototype card on tokens) — scoped risk-accepts & not-affected
 * calls. Decisions are immutable (D40): revoked rows stay, struck through; expiry never edits.
 * Revoke is gated by can_accept_audit_final (the server is the authority; the button follows).
 */
import { computed } from 'vue'

import ScannerTag from '@/components/chips/ScannerTag.vue'
import StateTag from '@/components/chips/StateTag.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'

export interface DecisionRow {
  decision_id: string
  type: string
  scope?: { namespaces?: string[]; images?: string[] }
  apply_both_scanners?: boolean
  scanner?: string | null
  approver?: string | null
  created_by?: string | null
  expiry?: string | null
  revoked_at?: string | null
  [key: string]: unknown
}

const props = defineProps<{
  decisions: DecisionRow[]
  canAcceptFinal: boolean
  busy: boolean
}>()
const emit = defineEmits<{ revoke: [id: string]; create: [] }>()

const rows = computed(() =>
  [...props.decisions].sort((a, b) => (a.revoked_at ? 1 : 0) - (b.revoked_at ? 1 : 0)),
)

function scopeLabel(d: DecisionRow): string {
  const ns = d.scope?.namespaces ?? []
  const im = d.scope?.images ?? []
  if (ns.length === 0 && im.length === 0) return 'cluster-wide'
  return [...ns, ...im].join(', ')
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <div>
        <h3>Decisions on this CVE</h3>
        <p class="card-sub">scoped risk-accept / not-affected RULES (immutable; edits revoke + re-create) — plain state changes are triage actions, listed under Activity</p>
      </div>
      <UiButton v-if="canAcceptFinal" @click="emit('create')">
        <AppIcon name="plus" :size="13" />New decision
      </UiButton>
    </div>
    <div class="card-body">
      <div class="dec-scroll">
      <table class="dtbl dtbl-bordered">
        <thead>
          <tr><th>Type</th><th>Scope</th><th>Scanners</th><th>By</th><th>Expiry</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-if="rows.length === 0">
            <td colspan="7" class="empty-row">No decisions on this CVE yet.</td>
          </tr>
          <tr v-for="d in rows" :key="d.decision_id" :class="{ 'dec-inactive': d.revoked_at }">
            <td><StateTag :state="d.type === 'risk_accepted' ? 'risk_accepted' : 'not_affected'" /></td>
            <td class="sm">{{ scopeLabel(d) }}</td>
            <td class="sm">
              <span v-if="d.apply_both_scanners" class="both-tag">both</span>
              <ScannerTag v-else-if="d.scanner" :name="d.scanner" />
            </td>
            <td class="sm">{{ d.approver ?? d.created_by ?? '—' }}</td>
            <td class="mono-cell sm">{{ d.expiry ?? '—' }}</td>
            <td>
              <span v-if="!d.revoked_at" class="dec-active">active</span>
              <span v-else class="dec-revoked">revoked</span>
            </td>
            <td class="c">
              <UiButton
                v-if="!d.revoked_at && canAcceptFinal"
                :disabled="busy"
                title="Revoke this decision (create a new one to replace it)"
                @click="emit('revoke', d.decision_id)"
              >
                Revoke
              </UiButton>
            </td>
          </tr>
        </tbody>
      </table>
      </div>
      <p v-if="decisions.length >= 50" class="cap-note">Showing the first 50 decisions. Older ones via the Audit screen (M9d).</p>
    </div>
  </section>
</template>

<style scoped>
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
  margin-top: var(--space-6); /* its own page band, not part of the evidence cluster */
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
.card-body {
  padding: 14px 16px;
  overflow-x: auto;
}
/* decisions must never become a page-length wall (same rule as images-affected) */
.dec-scroll {
  max-height: 340px;
  overflow-y: auto;
}
.dec-scroll thead th {
  position: sticky;
  top: 0;
  background: var(--card);
  z-index: 1;
}
.cap-note {
  margin: 10px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
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
.dtbl .sm {
  font-size: var(--text-sm);
}
.dtbl .c {
  text-align: center;
}
.mono-cell {
  font-family: var(--font-mono);
}
.empty-row {
  text-align: center;
  color: var(--soft);
  padding: 24px 12px;
}
.dec-inactive td {
  text-decoration: line-through;
  color: var(--soft);
}
.dec-inactive td .both-tag,
.dec-inactive td button {
  text-decoration: none;
}
.dec-active {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--state-resolved-fg);
}
.dec-revoked {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--soft);
}
.both-tag {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-chip);
  padding: 2px 7px;
  color: var(--ink);
}
</style>
