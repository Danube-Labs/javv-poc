<script setup lang="ts">
/**
 * The audit table (prototype screens-audit.jsx `AuditLog` table, ported per DESIGN.md §8 —
 * operator ruling 2026-07-12 superseding the timeline note: prototype grammar, shared skin):
 * When · User · Action · Target · Detail on `tbl tbl-dense tbl-hover`. Rows come in the
 * server's `(@timestamp, event_id)` walk and are re-read causally per page (`causalOrder`,
 * D38/H8): same-field edits display by `revision` (the `rev` badge). The Target column reads
 * the row's read-time decoration — CVE + severity + image for findings (the operator's "what
 * changed, on what"), CVE + type for decisions — and degrades to the bare entity id once the
 * doc ages out of the store (history outlives current state). Click-through only where
 * `entity_type === 'finding'` (A-5); the Task column is dropped (V4-DELTA-1, Jira = v1.1).
 */
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import { computed } from 'vue'

import { causalOrder } from '@/audit/causalOrder'
import ActionTag from '@/components/chips/ActionTag.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import SevChip from '@/components/chips/SevChip.vue'
import { lastDataAt } from '@/system/freshness'
import type { AuditEvent } from '@/stores/audit'

const props = defineProps<{
  rows: AuditEvent[]
  loading?: boolean
  filtered?: boolean
}>()
const emit = defineEmits<{ rowClick: [row: AuditEvent] }>()

const ordered = computed(() => causalOrder(props.rows))

const clickable = (e: AuditEvent) => e.entity_type === 'finding' && !!e.finding_key && !!e.finding

/** short mono identity fallback when a row has no decoration */
const shortId = (id: string) => (id.length > 16 ? `${id.slice(0, 12)}…` : id)

const shortImage = (e: AuditEvent) => (e.finding?.image_repo ?? '').split('/').pop() ?? ''

interface BulkJson {
  patch?: Record<string, unknown>
  target_ids?: string[]
  result_count?: number
}
const bulkJson = (e: AuditEvent): BulkJson | null =>
  e.action === 'bulk_triage' && e.new_value_json ? (e.new_value_json as BulkJson) : null

/** one-line what-changed; empty when the tag + target already say it all (auth events) */
function detail(e: AuditEvent): string {
  const bulk = bulkJson(e)
  if (bulk) {
    const patch = Object.entries(bulk.patch ?? {})
      .map(([k, v]) => `${k} → ${String(v)}`)
      .join(' · ')
    return `${patch} — ${bulk.result_count ?? '?'} findings (frozen set)`
  }
  if (e.field == null) return ''
  if (e.old_value == null && e.new_value == null) return ''
  if (e.old_value == null) return `${e.field}: ${e.new_value}`
  if (e.new_value == null) return `${e.field}: ${e.old_value} cleared`
  return `${e.field}: ${e.old_value} → ${e.new_value}`
}

function onRowClick(row: AuditEvent) {
  if (clickable(row)) emit('rowClick', row)
}
</script>

<template>
  <div class="tbl-wrap">
    <DataTable
      :value="ordered"
      lazy
      :loading="props.loading"
      data-key="event_id"
      :pt="{ table: { class: 'tbl tbl-dense tbl-hover' } }"
      @row-click="(e) => onRowClick(e.data as AuditEvent)"
    >
      <Column header="When" class="fit">
        <template #body="{ data }">
          <span class="mono-cell sm nowrap" :title="data['@timestamp']">{{ lastDataAt(data['@timestamp']) }}</span>
        </template>
      </Column>
      <Column header="User" class="fit">
        <template #body="{ data }">
          <span class="actor-cell">{{ data.actor }}</span>
        </template>
      </Column>
      <Column header="Action" class="fit">
        <template #body="{ data }">
          <ActionTag :action="data.action" />
        </template>
      </Column>
      <Column header="Target">
        <template #body="{ data }">
          <span v-if="data.finding" class="audit-target">
            <span class="mono-cell strong sm nowrap" :class="{ 'cve-link': clickable(data) }">{{ data.finding.cve_id }}</span>
            <SevChip v-if="data.finding.severity_canonical" :level="data.finding.severity_canonical" :dot="true" />
            <span class="mono-cell sm img-cell" :title="data.finding.image_repo ?? ''">{{ shortImage(data) }}</span>
            <ScannerTag v-if="data.finding.scanner" :name="data.finding.scanner" />
          </span>
          <span v-else-if="data.decision" class="audit-target">
            <span class="mono-cell strong sm nowrap">{{ data.decision.cve_id }}</span>
            <span class="target-kind">{{ data.decision.type === 'risk_accepted' ? 'risk accept' : (data.decision.type ?? 'decision') }}</span>
            <span class="target-kind">{{ data.decision.apply_both_scanners ? 'both scanners' : (data.decision.scanner ?? '') }}</span>
          </span>
          <span v-else class="audit-target">
            <span class="mono-cell sm" :title="data.entity_id">{{ shortId(data.entity_id) }}</span>
            <span class="target-kind">{{ data.entity_type }}</span>
          </span>
        </template>
      </Column>
      <Column header="Detail">
        <template #body="{ data }">
          <span class="detail-cell">
            <span class="wrap-cell soft" :title="detail(data)">{{ detail(data) || '-' }}</span>
            <span
              v-if="data.revision != null && data.field != null"
              class="rev-badge"
              title="Causal revision (D38): same-field edits replay by this, not arrival order"
              >rev {{ data.revision }}</span
            >
          </span>
        </template>
      </Column>
      <template #empty>
        <!-- while a fresh lens loads (rows just cleared), say loading — "no activity" would lie -->
        <div class="empty-row">
          {{ props.loading ? 'Loading events…'
            : filtered ? 'No events match these filters.'
            : 'No journaled activity for this cluster yet — triage actions, decisions and config edits will land here.' }}
        </div>
      </template>
    </DataTable>
  </div>
</template>

<style scoped>
/* the table skin (.tbl-wrap / .tbl family / empty-row) lives in base.css */
:deep(.actor-cell) {
  font-weight: 600;
  font-size: var(--text-sm);
  white-space: nowrap;
}
:deep(.audit-target) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
:deep(.target-kind) {
  font-size: var(--text-sm);
  color: var(--soft);
}
:deep(.detail-cell) {
  display: flex;
  align-items: center;
  gap: 8px;
}
:deep(.wrap-cell) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 46ch;
}
:deep(.soft) {
  color: var(--soft);
}
:deep(.rev-badge) {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--soft);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 0 5px;
  white-space: nowrap;
}
/* the affordance carrier, same grammar as the findings grid: the identifier lights up on a
   live row (only decorated finding rows navigate) */
:deep(.cve-link) {
  transition: color 0.12s ease-out;
}
:deep(.tbl-hover tbody tr:hover .cve-link) {
  color: var(--coral-text);
}
</style>
