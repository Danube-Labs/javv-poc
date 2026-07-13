<script setup lang="ts">
/**
 * Per-finding activity list (split from FindingDetailView, audit F-15): the audit-trail rows
 * for THIS finding_key — capped at a glance, the full trail lives on the Audit screen.
 */
import StateTag from '@/components/chips/StateTag.vue'
import { fmtAt } from '@/findings/format'

export interface ActivityRow {
  event_id: string
  action: string
  actor: string
  field?: string
  old_value?: string | null
  new_value?: string | null
  '@timestamp': string
}

defineProps<{ activity: ActivityRow[] }>()
</script>

<template>
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
</template>

<style scoped>
/* the detail-card chrome (scoped per component — the DecisionsCard idiom) */
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
.card-body {
  padding: 14px 16px;
  overflow-x: auto;
}
.mono-cell {
  font-family: var(--font-mono);
}
.sm {
  font-size: var(--text-sm);
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
.empty-row {
  text-align: center;
  color: var(--soft);
  padding: 28px 12px;
}
</style>
