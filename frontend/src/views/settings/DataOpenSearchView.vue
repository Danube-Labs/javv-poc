<script setup lang="ts">
/**
 * Data & OpenSearch panel (§13.7, FR-19/D26): the four knob groups (retention / rollover /
 * findings-cleanup / report-TTL) on one SaveBar — save PUTs only the changed groups
 * (`changedGroups`); the sweeps read the docs live, so edits apply at the next run. The
 * retention card lists EVERY index family (row 23): the append families share the ONE editable
 * window, protected families are read-only rows saying why. Snapshots (NFR-6) list + manual
 * take; restore lands in `restored-*` copies (double-confirmed — promoting one is a manual
 * step). The OpenSearch-runtime card is the §D read-only proxy display.
 */
import { computed, ref, watch } from 'vue'

import {
  getDataSettingsApiV1SettingsDataGet,
  getOpensearchRuntimeApiV1AdminOpensearchRuntimeGet,
  listSnapshotsApiV1AdminSnapshotsGet,
  putFindingsCleanupApiV1SettingsFindingsCleanupPut,
  putReportTtlApiV1SettingsReportTtlPut,
  putRetentionApiV1SettingsRetentionPut,
  putRolloverApiV1SettingsRolloverPut,
  restoreManualSnapshotApiV1AdminSnapshotsSnapshotNameRestorePost,
  takeManualSnapshotApiV1AdminSnapshotsPost,
} from '@/api/generated'
import { client } from '@/api/client'
import DotWord from '@/components/chips/DotWord.vue'
import SaveBar from '@/components/settings/SaveBar.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import SettingsRow from '@/components/settings/SettingsRow.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { logger } from '@/lib/logger'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'
import { lastDataAt } from '@/system/freshness'

import {
  changedGroups,
  draftDirty,
  draftFromKnobs,
  draftInvalid,
  FAMILY_ROWS,
  parseDraft,
  type DataDraft,
  type DataKnobs,
} from './dataForm'

interface SnapshotRow {
  snapshot: string
  state: string | null
  start_time: string | null
  end_time: string | null
  indices: number
  failures: number
}

interface RuntimeNode {
  name: string | null
  roles: string[]
  heap_used_mb: number
  heap_max_mb: number
  discovery_type: string | null
  path_repo: string | null
  security_enabled: boolean
}

interface Runtime {
  version: string | null
  distribution: string | null
  cluster_name: string | null
  status: string | null
  number_of_nodes: number
  active_shards: number
  nodes: RuntimeNode[]
}

const clusterStore = useClusterStore()
const auth = useAuthStore()
const toast = useToastStore()

// ── knobs (one SaveBar over the four groups) ────────────────────────────────────────────
const saved = ref<DataKnobs | null>(null)
const draft = ref<DataDraft>({
  retention: '',
  maxAge: '',
  maxDocs: '',
  maxSize: '',
  cleanup: '',
  ttl: '',
})
const override = ref(false)
const loading = ref(true)
const failed = ref(false)
const busy = ref(false)

// ── snapshots + runtime (read-side cards) ───────────────────────────────────────────────
const snapConfigured = ref(false)
const snapRepo = ref<string | null>(null)
const snapshots = ref<SnapshotRow[]>([])
const snapBusy = ref(false)
const restoreTarget = ref<string | null>(null)
const runtime = ref<Runtime | null>(null)

const canRestore = computed(() => auth.hasCapability('can_restore_snapshot'))

async function loadKnobs(clusterId: string) {
  loading.value = true
  const { data, response } = await getDataSettingsApiV1SettingsDataGet({
    client,
    query: { cluster_id: clusterId },
  })
  loading.value = false
  failed.value = !response?.ok
  if (failed.value || !data) {
    logger.warn('data_settings_load_failed', { status: response?.status })
    return
  }
  const body = data as unknown as {
    lifecycle: {
      retention_days: number
      max_age_days: number
      max_docs: number
      max_size_gb: number
    }
    per_cluster_override: boolean
    report_ttl_hours: number
    findings_cleanup: { cleanup_days: number }
  }
  saved.value = {
    retention_days: body.lifecycle.retention_days,
    max_age_days: body.lifecycle.max_age_days,
    max_docs: body.lifecycle.max_docs,
    max_size_gb: body.lifecycle.max_size_gb,
    cleanup_days: body.findings_cleanup.cleanup_days,
    report_ttl_hours: body.report_ttl_hours,
  }
  override.value = body.per_cluster_override
  draft.value = draftFromKnobs(saved.value)
}

async function loadSnapshots() {
  const { data, response } = await listSnapshotsApiV1AdminSnapshotsGet({ client })
  if (!response?.ok || !data) {
    logger.warn('snapshots_load_failed', { status: response?.status })
    return
  }
  const body = data as unknown as {
    configured: boolean
    repository: string | null
    snapshots: SnapshotRow[]
  }
  snapConfigured.value = body.configured
  snapRepo.value = body.repository
  snapshots.value = body.snapshots
}

async function loadRuntime() {
  const { data, response } = await getOpensearchRuntimeApiV1AdminOpensearchRuntimeGet({ client })
  if (!response?.ok || !data) {
    // the card is optional context — render nothing rather than a scary error
    logger.warn('opensearch_runtime_load_failed', { status: response?.status })
    return
  }
  runtime.value = data as unknown as Runtime
}

watch(
  () => clusterStore.selectedId,
  (id) => {
    if (!id) return
    void loadKnobs(id)
    void loadSnapshots()
    void loadRuntime()
  },
  { immediate: true },
)

const parsed = computed(() => parseDraft(draft.value))
const invalid = computed(() => draftInvalid(draft.value))
const dirty = computed(() => saved.value !== null && draftDirty(saved.value, draft.value))

async function save() {
  if (saved.value === null || invalid.value) return
  const p = parsed.value
  const groups = changedGroups(saved.value, draft.value)
  const clusterId = clusterStore.selectedId
  busy.value = true
  let allOk = true
  // per-cluster knobs edit the doc the effective read served (the staleness editor's rule);
  // cleanup + TTL are fleet-wide by design
  const clusterArg = override.value && clusterId ? { cluster_id: clusterId } : {}
  if (groups.retention) {
    const { response } = await putRetentionApiV1SettingsRetentionPut({
      client,
      body: { retention_days: p.retention_days!, ...clusterArg },
    })
    allOk &&= response?.ok ?? false
  }
  if (groups.rollover && allOk) {
    const { response } = await putRolloverApiV1SettingsRolloverPut({
      client,
      body: {
        max_age_days: p.max_age_days!,
        max_docs: p.max_docs!,
        max_size_gb: p.max_size_gb!,
        ...clusterArg,
      },
    })
    allOk &&= response?.ok ?? false
  }
  if (groups.cleanup && allOk) {
    const { response } = await putFindingsCleanupApiV1SettingsFindingsCleanupPut({
      client,
      body: { cleanup_days: p.cleanup_days! },
    })
    allOk &&= response?.ok ?? false
  }
  if (groups.ttl && allOk) {
    const { response } = await putReportTtlApiV1SettingsReportTtlPut({
      client,
      body: { hours: p.report_ttl_hours! },
    })
    allOk &&= response?.ok ?? false
  }
  busy.value = false
  if (!allOk) {
    logger.warn('data_settings_save_failed', {})
    toast.error('Saving failed — the store keeps the previous values. Reload to see what landed.')
    if (clusterId) void loadKnobs(clusterId) // partial saves must not fake a clean state
    return
  }
  saved.value = {
    retention_days: p.retention_days!,
    max_age_days: p.max_age_days!,
    max_docs: p.max_docs!,
    max_size_gb: p.max_size_gb!,
    cleanup_days: p.cleanup_days!,
    report_ttl_hours: p.report_ttl_hours!,
  }
  toast.success('Data settings saved — the daily sweeps apply them on their next run')
}

function discard() {
  if (saved.value !== null) draft.value = draftFromKnobs(saved.value)
}

async function snapshotNow() {
  snapBusy.value = true
  const { data, response } = await takeManualSnapshotApiV1AdminSnapshotsPost({ client })
  snapBusy.value = false
  if (!response?.ok || !data) {
    logger.warn('snapshot_take_failed', { status: response?.status })
    toast.error(
      response?.status === 409
        ? 'No snapshot repository configured — register one via the deploy first.'
        : 'Taking the snapshot failed.',
    )
    return
  }
  toast.success(`Snapshot ${(data as { snapshot: string }).snapshot} started`)
  void loadSnapshots()
}

async function confirmRestore() {
  const name = restoreTarget.value
  if (name === null) return
  restoreTarget.value = null
  snapBusy.value = true
  const { response } = await restoreManualSnapshotApiV1AdminSnapshotsSnapshotNameRestorePost({
    client,
    path: { snapshot_name: name },
  })
  snapBusy.value = false
  if (!response?.ok) {
    logger.warn('snapshot_restore_failed', { status: response?.status, snapshot: name })
    toast.error(
      response?.status === 403
        ? 'Restore needs the can_restore_snapshot capability.'
        : 'Restore failed — the live indices are untouched.',
    )
    return
  }
  toast.success(`Restoring ${name} into restored-* copies — nothing live is overwritten`)
}

function snapTone(state: string | null): 'ok' | 'warn' | 'down' | 'muted' {
  if (state === 'SUCCESS') return 'ok'
  if (state === 'IN_PROGRESS' || state === 'PARTIAL') return 'warn'
  if (state === 'FAILED') return 'down'
  return 'muted'
}

function healthTone(status: string | null): 'ok' | 'warn' | 'down' | 'muted' {
  if (status === 'green') return 'ok'
  if (status === 'yellow') return 'warn'
  if (status === 'red') return 'down'
  return 'muted'
}
</script>

<template>
  <div class="stack">
    <div class="scanner-banner">
      <AppIcon name="database" :size="14" />
      Retention retires whole time-partitioned indices at the horizon, never single documents.
      The daily lifecycle sweep reads these settings live, so an edit applies at its next run.
    </div>

    <div v-if="loading" class="skel-block" aria-busy="true" aria-label="Loading data settings" />
    <p v-else-if="failed" class="load-error" role="alert">
      Data settings unavailable. Check the backend connection.
    </p>

    <template v-else>
      <SettingsCard
        title="Retention"
        subtitle="one per-cluster window over the append families: how far back history and time-travel reach"
      >
        <SettingsRow
          label="Append-family retention"
          hint="Applies to the four append families below; expired indices are dropped whole by the daily sweep."
        >
          <SettingsInput
            id="ret-days"
            v-model="draft.retention"
            num
            unit="days"
            :invalid="parsed.retention_days === null"
          />
        </SettingsRow>
        <div class="tbl-wrap fam-wrap">
        <table class="tbl tbl-dense tbl-quiet tbl-hover">
          <thead>
            <tr>
              <th>Index family</th>
              <th>Holds</th>
              <th class="r">Retention</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="fam in FAMILY_ROWS" :key="fam.pattern" class="fam-row">
              <td class="mono">{{ fam.pattern }}</td>
              <td class="fam-note">{{ fam.purpose }}</td>
              <td class="r">
                <span v-if="fam.kind === 'append'" class="fam-window"
                  >{{ parsed.retention_days ?? saved?.retention_days }} days</span
                >
                <span v-else class="fam-guard" :title="fam.why">
                  <DotWord tone="muted" label="protected" />
                  <AppIcon name="info" :size="12" />
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        </div>
        <p class="fam-why-note">
          <b>Why one window, not per-family?</b> Time-travel rebuilds any past moment from
          occurrences, images and inventory runs <em>together</em>, so the app only reaches as
          far back as the <em>shortest</em> window — separate knobs would silently truncate
          reach to the minimum while still paying storage for the rest. Per-family windows are
          planned post-MVP. Protected families take no retention window at all — hover a
          <em>protected</em> tag for why.
        </p>
        <p class="scope-src">
          {{
            override
              ? "Editing THIS cluster's override — the fleet default stays untouched."
              : 'Editing the fleet-wide default (no override exists for this cluster).'
          }}
        </p>
      </SettingsCard>

      <SettingsCard
        title="Rollover thresholds"
        subtitle="when a write index rolls to a new one, whichever trips first"
      >
        <div class="roll-grid">
          <SettingsRow label="Max age" stack>
            <SettingsInput
              id="roll-age"
              v-model="draft.maxAge"
              num
              unit="days"
              :invalid="parsed.max_age_days === null"
            />
          </SettingsRow>
          <SettingsRow label="Max docs" stack>
            <SettingsInput
              id="roll-docs"
              v-model="draft.maxDocs"
              num
              unit="docs"
              :invalid="parsed.max_docs === null"
            />
          </SettingsRow>
          <SettingsRow label="Max primary size" stack>
            <SettingsInput
              id="roll-size"
              v-model="draft.maxSize"
              num
              unit="GB"
              :invalid="parsed.max_size_gb === null"
            />
          </SettingsRow>
        </div>
      </SettingsCard>

      <SettingsCard
        title="Cleanup & report retention"
        subtitle="fleet-wide windows, independent of the per-cluster retention above"
      >
        <SettingsRow
          label="Findings cleanup window"
          hint="Cache rows whose image has been gone this long are deleted (history is untouched). The cleanup job ships with the final M9e slice; the window takes effect then."
        >
          <SettingsInput
            id="cleanup-days"
            v-model="draft.cleanup"
            num
            unit="days"
            :invalid="parsed.cleanup_days === null"
          />
        </SettingsRow>
        <SettingsRow
          label="Report/export retention"
          hint="A completed export is deleted this long after it finishes; a download past it returns 410."
        >
          <SettingsInput
            id="report-ttl"
            v-model="draft.ttl"
            num
            unit="hours"
            :invalid="parsed.report_ttl_hours === null"
          />
        </SettingsRow>
      </SettingsCard>
    </template>

    <SettingsCard title="Snapshots" subtitle="native OpenSearch snapshot/restore — the durability set (NFR-6)">
      <template v-if="!snapConfigured">
        <p class="snap-unconfigured">
          No snapshot repository is configured. Register one via the deploy: credentials live in
          the OpenSearch keystore, and only the non-secret repo reference lands in system-config.
        </p>
      </template>
      <template v-else>
        <SettingsRow label="Repository">
          <span class="mono">{{ snapRepo }}</span>
        </SettingsRow>
        <SettingsRow
          label="Manual snapshot"
          hint="Snapshots the current-state + config indices on demand; the scheduled policy keeps running either way."
        >
          <UiButton variant="control" :disabled="snapBusy" @click="snapshotNow">
            <AppIcon name="database" :size="13" />
            Snapshot now
          </UiButton>
        </SettingsRow>
        <div v-if="snapshots.length" class="tbl-wrap snap-wrap">
        <table class="tbl tbl-dense tbl-quiet tbl-hover">
          <thead>
            <tr>
              <th>Snapshot</th>
              <th>State</th>
              <th>Started</th>
              <th>Ended</th>
              <th class="r">Indices</th>
              <th class="fit"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in snapshots" :key="s.snapshot">
              <td class="mono">{{ s.snapshot }}</td>
              <td><DotWord :tone="snapTone(s.state)" :label="s.state ?? 'unknown'" /></td>
              <td class="mono">{{ lastDataAt(s.start_time) }}</td>
              <td class="mono">{{ lastDataAt(s.end_time) }}</td>
              <td class="r">{{ s.indices }}</td>
              <td class="fit">
                <UiButton
                  v-if="canRestore"
                  variant="quiet"
                  :disabled="snapBusy || s.state !== 'SUCCESS'"
                  @click="restoreTarget = s.snapshot"
                >
                  Restore…
                </UiButton>
              </td>
            </tr>
          </tbody>
        </table>
        </div>
        <p v-else class="snap-unconfigured">No snapshots in the repository yet.</p>
      </template>
    </SettingsCard>

    <SettingsCard
      v-if="runtime"
      title="OpenSearch runtime"
      subtitle="read-only: static settings are deploy-owned (GitOps); anything displayable is displayed"
    >
      <div class="stat-band stat-band--stat rt-band">
        <div class="stat-cell">
          <span class="stat-label">Version</span>
          <span class="stat-num">{{ runtime.distribution }} {{ runtime.version }}</span>
        </div>
        <div class="stat-cell">
          <span class="stat-label">Cluster</span>
          <span class="stat-num">{{ runtime.cluster_name }}</span>
          <span class="stat-sub">
            <DotWord :tone="healthTone(runtime.status)" :label="runtime.status ?? 'unknown'" />
          </span>
        </div>
        <div class="stat-cell">
          <span class="stat-label">Topology</span>
          <span class="stat-num"
            >{{ runtime.number_of_nodes }}
            {{ runtime.number_of_nodes === 1 ? 'node' : 'nodes' }}</span
          >
          <span class="stat-sub">{{ runtime.active_shards }} active shards</span>
        </div>
      </div>
      <div class="tbl-wrap rt-wrap">
        <table class="tbl tbl-dense tbl-quiet tbl-hover">
          <thead>
            <tr>
              <th>Node</th>
              <th>Roles</th>
              <th class="r">JVM heap</th>
              <th>Discovery</th>
              <th>Snapshot path</th>
              <th>Security</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="n in runtime.nodes" :key="n.name ?? ''">
              <td class="mono">{{ n.name }}</td>
              <td>{{ n.roles.join(', ') || '—' }}</td>
              <td class="mono r">{{ n.heap_used_mb }} / {{ n.heap_max_mb }} MB</td>
              <td class="mono">{{ n.discovery_type ?? '—' }}</td>
              <td class="mono">{{ n.path_repo ?? 'unset' }}</td>
              <td>{{ n.security_enabled ? 'enabled' : 'disabled' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </SettingsCard>

    <SaveBar
      v-if="!loading && !failed"
      :dirty="dirty"
      :invalid="invalid"
      :busy="busy"
      @save="save"
      @discard="discard"
    />

    <ModalShell
      v-if="restoreTarget !== null"
      title="Restore snapshot"
      :subtitle="restoreTarget"
      @close="restoreTarget = null"
    >
      <p class="restore-copy">
        Restores every index in <span class="mono">{{ restoreTarget }}</span> into fresh
        <span class="mono">restored-*</span> copies. <b>Nothing live is overwritten</b>:
        promoting a restored copy is a deliberate manual step. The action is journaled.
      </p>
      <div class="restore-actions">
        <UiButton variant="quiet" @click="restoreTarget = null">Cancel</UiButton>
        <UiButton variant="primary" @click="confirmRestore">Restore into copies</UiButton>
      </div>
    </ModalShell>
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.scanner-banner {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: var(--text-sweep-strong);
  color: var(--ink);
  background: var(--note-info-bg);
  border: 1px solid var(--note-info-line);
  border-radius: 9px;
  padding: 9px 12px;
  line-height: 1.45;
}
.scanner-banner svg {
  flex: none;
  color: var(--teal);
}
/* in-card tables run FULL-BLEED to the card edges (the ui.nuxt/GitHub settings grammar,
   operator 2026-07-16): the card is the container — a bordered box floating inside a padded
   card reads as border-in-border. The card's 16px side padding is cancelled, the head band
   spans edge to edge, and only hairlines separate the table from the card body. */
/* the preceding set-row already draws the hairline — the table adds NO top border of its
   own (the head band's color shift is the opening cue); a bottom hairline only where prose
   follows the table (fam), never against the card's own edge (snap runs flush) */
.fam-wrap {
  margin: 14px -16px 0;
  border: 0;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
  box-shadow: none;
}
.snap-wrap {
  margin: 14px -16px -14px;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}
.fam-note {
  color: var(--soft);
}
.fam-window {
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.fam-guard {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  cursor: help;
}
.fam-guard svg {
  color: var(--soft);
}
.fam-why-note,
.scope-src {
  margin: 10px 0 2px;
  font-size: var(--text-sm);
  color: var(--soft);
}
.snap-unconfigured {
  margin: 14px 0 8px;
  font-size: var(--text-body);
  color: var(--soft);
}
.snap-tbl {
  margin-top: 14px;
}
/* rollover: three small numbers earn one row, not three full-width ones */
.roll-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 18px;
}
.roll-grid :deep(.set-row) {
  border-bottom: 0;
}
@media (max-width: 720px) {
  .roll-grid {
    grid-template-columns: 1fr;
  }
}
.rt-inline {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}
/* the cluster facts ride the shared stat-band, full-bleed and FLUSH under the card head —
   the head's own hairline is the only separator (no border + gap + border stacks) */
.rt-band {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: -4px -16px 0;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}
.rt-wrap {
  margin: 0 -16px -14px;
  border: 0;
  border-top: 1px solid var(--line);
  border-radius: 0;
  box-shadow: none;
}
.restore-copy {
  margin: 0 0 16px;
  line-height: 1.5;
  color: var(--ink);
}
.restore-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.load-error {
  margin: 14px 0 8px;
}
.skel-block {
  height: 180px;
  border-radius: var(--r-sm);
  background: linear-gradient(90deg, var(--line2) 25%, var(--panel) 50%, var(--line2) 75%);
  background-size: 200% 100%;
  animation: skel-shimmer 1.4s ease-in-out infinite;
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
  .skel-block {
    animation: none;
  }
}
</style>
