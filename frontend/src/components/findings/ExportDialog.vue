<script setup lang="ts">
/**
 * Export the current lens (M9b slice 4, C-2 states). Run-now streams inline (413 past
 * JAVV_EXPORT_MAX_ROWS → offer the schedule path); Schedule enqueues an off-peak report and
 * polls to the signed download link with its expiry. VEX is per-scanner by contract (one
 * scanner per file — per-scanner sacred). Exports describe CURRENT state: at T<now the dialog
 * is read-only (the export-at-past-T seam lands with a later slice). Schedule params carry no
 * namespace/ptype — those lenses BLOCK scheduling rather than silently widening.
 */
import { computed, onUnmounted, ref } from 'vue'

import { enqueueReportApiV1ReportsPost, getReportApiV1ReportsReportIdGet } from '@/api/generated'
import AppIcon from '@/components/ui/AppIcon.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import { useApi } from '@/composables/useApi'
import { buildFilterQuery } from '@/filters/buildFilterQuery'
import type { FilterField } from '@/filters/fields.config'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{
  fields: readonly FilterField[]
  selections: Record<string, string[]>
  historical: boolean
}>()
const clusterStore = useClusterStore()
const toast = useToastStore()
const { withGlobals } = useApi()

const open = ref(false)
const tab = ref<'now' | 'schedule'>('now')
const format = ref<'csv' | 'vex'>('csv')
const vexScanner = ref<'trivy' | 'grype'>('trivy')
const TAB_OPTS = [
  { value: 'now', label: 'Run now' },
  { value: 'schedule', label: 'Schedule off-peak' },
] as const
const FORMAT_OPTS = [
  { value: 'csv', label: 'CSV' },
  { value: 'vex', label: 'VEX (OpenVEX)' },
] as const
const SCANNER_OPTS = [
  { value: 'trivy', label: 'trivy' },
  { value: 'grype', label: 'grype' },
] as const
const busy = ref(false)
const error = ref<string | null>(null)
const report = ref<{ id: string; status: string; token?: string; expires_at?: string } | null>(null)
let poll: ReturnType<typeof setInterval> | null = null

const timeTravel = useTimeTravelStore()
const lensQuery = computed(() =>
  buildFilterQuery(props.fields, props.selections, {
    ...withGlobals(),
    window_days: timeTravel.windowDays,
  }),
)
/** ExportParams has no namespace/ptype — a lens using them cannot be scheduled faithfully. */
const scheduleBlocked = computed(() => {
  const q = lensQuery.value as Record<string, unknown>
  const offenders = ['namespace', 'ptype'].filter((k) => q[k] !== undefined)
  return offenders.length
    ? `${offenders.join(', ')} filter(s) are not part of scheduled-export params — ` +
        'clear them or use Run now.'
    : null
})

function openDialog() {
  error.value = null
  report.value = null
  tab.value = 'now'
  open.value = true
}
function close() {
  open.value = false
  if (poll) clearInterval(poll)
  poll = null
}
onUnmounted(() => {
  if (poll) clearInterval(poll)
})

/* ---- run now: fetch → blob → download (so 413/501 surface as messages, not broken tabs) ---- */
async function runNow() {
  busy.value = true
  error.value = null
  const q = { ...lensQuery.value } as Record<string, unknown>
  const path = format.value === 'csv' ? 'export.csv' : 'export.vex'
  if (format.value === 'vex') q.scanner = vexScanner.value
  const qs = new URLSearchParams(
    Object.entries(q).flatMap(([k, v]) =>
      v === undefined || v === null
        ? []
        : Array.isArray(v)
          ? v.map((x) => [k, String(x)] as [string, string])
          : [[k, String(v)] as [string, string]],
    ),
  )
  const resp = await fetch(`/api/v1/findings/${path}?${qs}`, { credentials: 'same-origin' })
  busy.value = false
  if (resp.status === 413) {
    error.value = 'Over the inline export cap — narrow the lens, or schedule it off-peak.'
    tab.value = 'schedule'
    return
  }
  if (!resp.ok) {
    error.value = `Export failed (${resp.status}) — check the backend connection.`
    logger.warn('export_failed', { status: resp.status })
    return
  }
  const blob = await resp.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `javv-findings-${new Date().toISOString().slice(0, 10)}.${format.value === 'csv' ? 'csv' : 'openvex.json'}`
  a.click()
  URL.revokeObjectURL(a.href)
  logger.info('export_downloaded', { format: format.value })
  toast.success(`Export downloaded · ${a.download}`)
}

/* ---- schedule: enqueue → poll status → signed download link + expiry ---- */
function expiresIn(iso?: string): string {
  if (!iso) return ''
  const h = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 3_600_000))
  return `expires in ~${h}h`
}
async function schedule() {
  busy.value = true
  error.value = null
  const q = lensQuery.value as Record<string, unknown>
  const response = await enqueueReportApiV1ReportsPost({
    body: {
      kind: 'export',
      cluster_id: clusterStore.selectedId!,
      run_mode: 'offpeak',
      params: {
        format: format.value === 'csv' ? 'csv' : 'openvex',
        ...(format.value === 'vex' ? { scanner: vexScanner.value } : {}),
        ...(q.severity !== undefined ? { severity: q.severity } : {}),
        ...(q.state !== undefined ? { state: q.state } : {}),
        ...(format.value === 'csv' && q.scanner !== undefined ? { scanner: q.scanner } : {}),
        ...(q.assignee !== undefined ? { assignee: q.assignee } : {}),
        ...(q.kev !== undefined ? { kev: q.kev } : {}),
        ...(q.fixable !== undefined ? { fixable: q.fixable } : {}),
        ...(q.disagree !== undefined ? { disagree: q.disagree } : {}),
        ...(q.image_repo !== undefined ? { image_repo: q.image_repo } : {}),
      },
    } as never,
  })
  busy.value = false
  if (response.response?.ok && response.data) {
    const body = response.data as { report_id: string; status: string }
    report.value = { id: body.report_id, status: body.status }
    poll = setInterval(() => void checkReport(), 5_000)
  } else {
    error.value = 'Could not schedule — check the backend connection.'
    logger.warn('export_schedule_failed', { status: response.response?.status })
  }
}
async function checkReport() {
  if (!report.value) return
  const response = await getReportApiV1ReportsReportIdGet({ path: { report_id: report.value.id } })
  if (!response.response?.ok || !response.data) return
  const body = response.data as {
    status: string
    download_token?: string
    expires_at?: string
  }
  report.value = {
    id: report.value.id,
    status: body.status,
    token: body.download_token,
    expires_at: body.expires_at,
  }
  if (body.status === 'done' || body.status === 'failed') {
    if (poll) clearInterval(poll)
    poll = null
  }
}
const downloadHref = computed(() =>
  report.value?.token
    ? `/api/v1/reports/${report.value.id}/download?token=${encodeURIComponent(report.value.token)}`
    : null,
)
</script>

<template>
  <div class="export-wrap">
    <UiButton variant="control" @click="openDialog">
      <AppIcon name="download" :size="13" />Export
    </UiButton>

    <ModalShell
      v-if="open"
      title="Export"
      subtitle="the current lens · per-scanner sacred (VEX = one scanner per file)"
      :width="480"
      @close="close"
    >
          <p v-if="historical" class="ex-blocked">
            <AppIcon name="clock" :size="13" />
            Exports describe current state — return to now to export. (Past-T exports land with
            reconstruction sweeps.)
          </p>
          <template v-else>
            <UiSegControl v-model="tab" class="tabs" :options="TAB_OPTS" />

            <UiField label="Format">
              <UiSegControl v-model="format" :options="FORMAT_OPTS" />
            </UiField>
            <div v-if="format === 'vex'" class="vex-scanner">
              <UiField label="Scanner (one per VEX file)">
                <UiSegControl v-model="vexScanner" :options="SCANNER_OPTS" />
              </UiField>
            </div>

            <template v-if="tab === 'now'">
              <p class="ex-note">Streams up to the inline cap; a bigger lens gets a 413 and the schedule path.</p>
            </template>
            <template v-else>
              <p v-if="scheduleBlocked" class="ex-blocked"><AppIcon name="alert" :size="13" /> {{ scheduleBlocked }}</p>
              <p v-else class="ex-note">Runs in the off-peak window; the result keeps for ~24h after completion.</p>
              <div v-if="report" class="report-status">
                <template v-if="report.status === 'done' && downloadHref">
                  <AppIcon name="check" :size="13" />
                  <a :href="downloadHref" class="dl-link">Download</a>
                  <span class="ex-dim">{{ expiresIn(report.expires_at) }}</span>
                </template>
                <template v-else-if="report.status === 'failed'">
                  <AppIcon name="alert" :size="13" /> Report failed — re-run the export.
                </template>
                <template v-else>
                  <AppIcon name="clock" :size="13" /> Scheduled — status: {{ report.status }}…
                </template>
              </div>
            </template>

            <p v-if="error" class="ex-error" role="alert">{{ error }}</p>
          </template>

      <template #actions>
          <UiButton variant="ghost" @click="close">Close</UiButton>
          <UiButton
            v-if="!historical && tab === 'now'"
            variant="primary"
            :disabled="busy"
            @click="runNow"
          >
            {{ busy ? 'Exporting…' : 'Download' }}
          </UiButton>
          <UiButton
            v-else-if="!historical"
            variant="primary"
            :disabled="busy || !!scheduleBlocked || report !== null"
            @click="schedule"
          >
            {{ busy ? 'Scheduling…' : 'Schedule' }}
          </UiButton>
      </template>
    </ModalShell>
  </div>
</template>

<style scoped>
.export-wrap {
  display: inline-flex;
}
.tabs {
  margin-bottom: 4px;
}
.vex-scanner {
  margin-top: 2px;
}
.ex-note {
  margin: 12px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.5;
}
.ex-blocked {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin: 10px 0 0;
  font-size: var(--text-body);
  color: var(--ink);
  background: var(--hist-bg);
  border: 1px solid var(--hist-line);
  border-radius: var(--r-sm);
  padding: 10px 12px;
  line-height: 1.5;
}
.ex-blocked svg {
  flex: none;
  margin-top: 2px;
  color: var(--hist-fg);
}
.report-status {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 12px;
  font-size: var(--text-body);
  color: var(--ink);
}
.dl-link {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.ex-dim {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--soft);
}
.ex-error {
  margin: 10px 0 0;
  font-size: var(--text-sm);
  color: var(--health-down-fg);
}
</style>
