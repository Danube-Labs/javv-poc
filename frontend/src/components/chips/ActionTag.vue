<script setup lang="ts">
/**
 * Audit action pill (prototype screens-audit.jsx `ActionTag`, restyled onto chip language A):
 * workflow verbs read in the QUIET register — StateTag's soft-tint + lifecycle-dot grammar,
 * with triage verbs wearing their target state's tone and every non-triage event a warm
 * neutral. Palette comes from tokens (DESIGN.md §8: port structure, never palette).
 */
import { computed } from 'vue'

const LABELS: Record<string, string> = {
  reopen: 'Reopened',
  acknowledge: 'Acknowledged',
  not_affected: 'Not affected',
  risk_accept: 'Risk accepted',
  resolve: 'Resolved',
  assign: 'Assigned',
  note: 'Note',
  bulk_triage: 'Bulk triage',
  decision_create: 'Decision created',
  decision_revoke: 'Decision revoked',
  view_create: 'View created',
  view_update: 'View updated',
  view_delete: 'View deleted',
  sla_policy_change: 'SLA policy',
  cluster_rename: 'Cluster renamed',
  pwd_change: 'Password changed',
  pwd_reset: 'Password reset',
  role_change: 'Role changed',
  user_create: 'User created',
  user_enable: 'User enabled',
  user_disable: 'User disabled',
  token_mint: 'Token minted',
  token_revoke: 'Token revoked',
  login: 'Login',
  logout: 'Logout',
}

/** triage verb → the state tone it lands the finding in */
const TONES: Record<string, string> = {
  reopen: 'open',
  acknowledge: 'ack',
  not_affected: 'na',
  risk_accept: 'risk',
  resolve: 'resolved',
}

const props = defineProps<{ action: string }>()
const label = computed(() => LABELS[props.action] ?? props.action.replace(/_/g, ' '))
const tone = computed(() => TONES[props.action] ?? 'neutral')
</script>

<template>
  <span class="action-tag" :data-tone="tone">
    <i class="at-dot" aria-hidden="true" />{{ label }}
  </span>
</template>

<style scoped>
.action-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-sm);
  font-weight: 500;
  padding: 3px 10px;
  border-radius: 999px;
  white-space: nowrap;
}
.at-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
}
.action-tag[data-tone='open'] { background: var(--state-open-bg); color: var(--state-open-fg); }
.action-tag[data-tone='open'] .at-dot { background: var(--state-open-solid); }
.action-tag[data-tone='ack'] { background: var(--state-ack-bg); color: var(--state-ack-fg); }
.action-tag[data-tone='ack'] .at-dot { background: var(--state-ack-solid); }
.action-tag[data-tone='na'] { background: var(--state-na-bg); color: var(--state-na-fg); }
.action-tag[data-tone='na'] .at-dot { background: var(--state-na-solid); }
.action-tag[data-tone='risk'] { background: var(--state-risk-bg); color: var(--state-risk-fg); }
.action-tag[data-tone='risk'] .at-dot { background: var(--state-risk-solid); }
.action-tag[data-tone='resolved'] { background: var(--state-resolved-bg); color: var(--state-resolved-fg); }
.action-tag[data-tone='resolved'] .at-dot { background: var(--state-resolved-solid); }
.action-tag[data-tone='neutral'] { background: var(--line2); color: var(--soft); }
.action-tag[data-tone='neutral'] .at-dot { background: var(--muted); }
</style>
