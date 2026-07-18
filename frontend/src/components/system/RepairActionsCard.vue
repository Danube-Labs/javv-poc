<script setup lang="ts">
/**
 * Repair actions (issue 406 — the mockup's third card, backed by /api/v1/admin/jobs):
 * "something looks broken" never means raw writes — the three sanctioned, journaled jobs are
 * the fix. Rows: icon tile · name + capability sub · description · status (state chip, the
 * in-flight bar, last-result counts, stale-lease honesty) · the run button. Lifecycle DROPS
 * whole indices, so its button confirms through ModalShell first. Polls while anything runs.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { client } from '@/api/client'
import { listJobsApiV1AdminJobsGet, triggerJobApiV1AdminJobsKindRunPost } from '@/api/generated'
import AppIcon, { type IconName } from '@/components/ui/AppIcon.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { fmtAt } from '@/findings/format'
import { logger } from '@/lib/logger'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { fmtJobResult } from '@/system/inspect'

interface JobDoc {
  kind: string
  status: 'idle' | 'running' | 'done' | 'failed'
  capability: string
  stale: boolean
  requested_by?: string | null
  started_at?: string | null
  finished_at?: string | null
  result?: Record<string, unknown> | null
  error?: string | null
}

const COPY: Record<string, { icon: IconName; label: string; sub: string; desc: string }> = {
  rebuild_state: {
    icon: 'rescan',
    label: 'Rebuild state',
    sub: 'findings cache · presence · sla clocks',
    desc: 'Re-derives every materialized row from the append history — the crash self-heal. Safe to run any time; history is never touched.',
  },
  staleness_sweep: {
    icon: 'clock',
    label: 'Staleness sweep',
    sub: 'two-timer pass',
    desc: 'Re-evaluates stale flags now instead of waiting for the scheduled run.',
  },
  lifecycle_sweep: {
    icon: 'trash',
    label: 'Lifecycle sweep',
    sub: 'retention · whole-index drops',
    desc: 'Applies retention by dropping whole aged indices — the only sanctioned delete in the system.',
  },
}

const auth = useAuthStore()
const toast = useToastStore()
const jobs = ref<JobDoc[]>([])
const loaded = ref(false)
const failed = ref(false)
const confirming = ref<JobDoc | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

async function refresh() {
  const r = await listJobsApiV1AdminJobsGet({ client })
  if (r.response?.ok && r.data) {
    jobs.value = (r.data as { jobs: JobDoc[] }).jobs
    failed.value = false
  } else {
    failed.value = true
  }
  loaded.value = true
  syncPolling()
}

const anyRunning = computed(() => jobs.value.some((j) => j.status === 'running' && !j.stale))

function syncPolling() {
  if (anyRunning.value && timer === null) {
    timer = setInterval(() => void refresh(), 3000)
  } else if (!anyRunning.value && timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(() => void refresh())
onUnmounted(() => {
  if (timer !== null) clearInterval(timer)
})

function requestRun(job: JobDoc) {
  if (job.kind === 'lifecycle_sweep') {
    confirming.value = job // destructive tier — say what it deletes before it deletes
  } else {
    void run(job)
  }
}

async function run(job: JobDoc) {
  confirming.value = null
  const r = await triggerJobApiV1AdminJobsKindRunPost({ client, path: { kind: job.kind } })
  if (r.response?.status === 202) {
    logger.info('repair_job_triggered', { kind: job.kind })
    await refresh()
  } else {
    const problem = (r.error ?? null) as { title?: string } | null
    toast.info(problem?.title ?? `${COPY[job.kind]?.label ?? job.kind} could not start.`)
    logger.warn('repair_job_rejected', { kind: job.kind, status: r.response?.status })
    await refresh() // a 409 means someone else is running it — show that truth
  }
}

function statusMeta(job: JobDoc): string {
  if (job.status === 'running' && job.stale)
    return `no heartbeat since ${fmtAt(job.started_at)} — reclaimable, run again`
  if (job.status === 'running') return `running · by ${job.requested_by} · since ${fmtAt(job.started_at)}`
  if (job.status === 'done') return `${fmtAt(job.finished_at)} · ${fmtJobResult(job.result)}`
  if (job.status === 'failed') return `failed ${fmtAt(job.finished_at)} — ${job.error ?? 'see backend logs'}`
  return 'never run on this store'
}

function canRun(job: JobDoc): boolean {
  return auth.hasCapability(job.capability)
}
</script>

<template>
  <section class="card repair">
    <h3 class="panel-band">Repair actions</h3>
    <p class="repair-sub">
      "Something looks broken" never means raw writes — the store is append-only and journaled,
      so repair runs through the sanctioned jobs. Every trigger lands in the audit log.
    </p>
    <p v-if="failed" class="load-error" role="alert">
      Job status unavailable — the triggers are disabled until it loads.
    </p>
    <template v-else-if="loaded">
      <div v-for="job in jobs" :key="job.kind" class="repair-row">
        <span class="repair-tile"><AppIcon :name="COPY[job.kind]?.icon ?? 'gear'" :size="16" /></span>
        <div class="repair-name">
          <b>{{ COPY[job.kind]?.label ?? job.kind }}</b>
          <span>{{ COPY[job.kind]?.sub }}</span>
        </div>
        <p class="repair-desc">{{ COPY[job.kind]?.desc }}</p>
        <div class="repair-status">
          <div v-if="job.status === 'running' && !job.stale" class="job-runbar" aria-hidden="true" />
          <p class="job-meta" :class="{ 'job-failed': job.status === 'failed' || job.stale }">
            {{ statusMeta(job) }}
          </p>
        </div>
        <UiButton
          :variant="job.status === 'running' && !job.stale ? 'control' : 'primary'"
          :disabled="!canRun(job) || (job.status === 'running' && !job.stale)"
          :title="canRun(job) ? undefined : `Requires ${job.capability}`"
          @click="requestRun(job)"
        >
          {{ job.status === 'running' && !job.stale ? 'Running…' : 'Run' }}
        </UiButton>
      </div>
    </template>

    <ModalShell v-if="confirming" title="Run the lifecycle sweep?" @close="confirming = null">
      <p class="confirm-body">
        This applies retention by <b>deleting whole aged indices</b> — findings history past each
        cluster's retention window is gone for good, and time-travel can no longer reach it.
        The sweep is journaled and follows the same rules as the scheduled run.
      </p>
      <template #actions>
        <UiButton variant="control" @click="confirming = null">Cancel</UiButton>
        <UiButton variant="primary" @click="run(confirming)">Run the sweep</UiButton>
      </template>
    </ModalShell>
  </section>
</template>

<style scoped>
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.repair {
  margin-top: var(--space-6);
}
.panel-band {
  margin: 0;
  padding: 10px 16px;
  background: var(--table-head-bg);
  color: var(--table-head-fg);
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
.repair-sub {
  color: var(--soft);
  font-size: var(--text-body);
  margin: 12px 16px 8px;
  max-width: 88ch;
}
.load-error {
  margin: 4px 16px 12px;
}
.repair-row {
  display: grid;
  grid-template-columns: 34px 200px 1fr 300px 110px;
  gap: 16px;
  align-items: center;
  padding: 12px 16px;
  border-top: 1px solid var(--line2);
}
.repair-row:hover {
  background: var(--panel);
}
.repair-tile {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--r-sm);
  background: var(--panel);
  border: 1px solid var(--line2);
  color: var(--soft);
}
.repair-name b {
  display: block;
  font-size: var(--text-body);
}
.repair-name span {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  color: var(--soft);
}
.repair-desc {
  margin: 0;
  color: var(--soft);
  font-size: var(--text-sm);
}
/* the in-flight indicator — the same infinite-bar grammar as the console's runbar; result
   counts land the moment the run finishes (no per-row percentage: the jobs report counts,
   not progress — honest over decorative) */
.job-runbar {
  height: 4px;
  border-radius: 2px;
  background: var(--line2);
  overflow: hidden;
  position: relative;
  margin-bottom: 5px;
}
.job-runbar::after {
  content: '';
  position: absolute;
  inset: 0;
  width: 38%;
  background: var(--coral);
  border-radius: 2px;
  animation: repair-sweep 1.1s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
@keyframes repair-sweep {
  from {
    transform: translateX(-110%);
  }
  to {
    transform: translateX(300%);
  }
}
@media (prefers-reduced-motion: reduce) {
  .job-runbar::after {
    animation: none;
    width: 100%;
    opacity: 0.45;
  }
}
.job-meta {
  margin: 0;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  color: var(--soft);
  overflow-wrap: anywhere;
}
.job-failed {
  color: var(--health-down-fg);
}
.repair-row .ui-btn {
  justify-self: end;
}
.confirm-body {
  margin: 0;
  color: var(--soft);
  font-size: var(--text-body);
  max-width: 60ch;
}
.confirm-body b {
  color: var(--ink);
}
</style>
