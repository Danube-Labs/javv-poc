<script setup lang="ts">
/**
 * Snapshots card (§13.7, NFR-6) — self-contained: list + manual take + restore. The repo is
 * fleet-global (one durability set), so one load serves every cluster. Restore lands in
 * `restored-*` copies behind a double-confirm — nothing live is ever overwritten; the button
 * renders only with can_restore_snapshot. Both actions are journaled server-side.
 */
import { computed, ref } from 'vue'

import {
  listSnapshotsApiV1AdminSnapshotsGet,
  restoreManualSnapshotApiV1AdminSnapshotsSnapshotNameRestorePost,
  takeManualSnapshotApiV1AdminSnapshotsPost,
} from '@/api/generated'
import { client } from '@/api/client'
import DotWord from '@/components/chips/DotWord.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsRow from '@/components/settings/SettingsRow.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { logger } from '@/lib/logger'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { lastDataAt } from '@/system/freshness'

interface SnapshotRow {
  snapshot: string
  state: string | null
  start_time: string | null
  end_time: string | null
  indices: number
  failures: number
}

const auth = useAuthStore()
const toast = useToastStore()

const configured = ref(false)
const repo = ref<string | null>(null)
const snapshots = ref<SnapshotRow[]>([])
const busy = ref(false)
const restoreTarget = ref<string | null>(null)

const canRestore = computed(() => auth.hasCapability('can_restore_snapshot'))

async function load() {
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
  configured.value = body.configured
  repo.value = body.repository
  snapshots.value = body.snapshots
}
void load()

async function snapshotNow() {
  busy.value = true
  const { data, response } = await takeManualSnapshotApiV1AdminSnapshotsPost({ client })
  busy.value = false
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
  void load()
}

async function confirmRestore() {
  const name = restoreTarget.value
  if (name === null) return
  restoreTarget.value = null
  busy.value = true
  const { response } = await restoreManualSnapshotApiV1AdminSnapshotsSnapshotNameRestorePost({
    client,
    path: { snapshot_name: name },
  })
  busy.value = false
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

function tone(state: string | null): 'ok' | 'warn' | 'down' | 'muted' {
  if (state === 'SUCCESS') return 'ok'
  if (state === 'IN_PROGRESS' || state === 'PARTIAL') return 'warn'
  if (state === 'FAILED') return 'down'
  return 'muted'
}
</script>

<template>
  <SettingsCard
    title="Snapshots"
    subtitle="native OpenSearch snapshot/restore — the durability set (NFR-6)"
  >
    <template v-if="!configured">
      <p class="snap-unconfigured">
        No snapshot repository is configured. Register one via the deploy: credentials live in
        the OpenSearch keystore, and only the non-secret repo reference lands in system-config.
      </p>
    </template>
    <template v-else>
      <SettingsRow label="Repository">
        <span class="mono">{{ repo }}</span>
      </SettingsRow>
      <SettingsRow
        label="Manual snapshot"
        hint="Snapshots the current-state + config indices on demand; the scheduled policy keeps running either way."
      >
        <UiButton variant="control" :disabled="busy" @click="snapshotNow">
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
              <td><DotWord :tone="tone(s.state)" :label="s.state ?? 'unknown'" /></td>
              <td class="mono">{{ lastDataAt(s.start_time) }}</td>
              <td class="mono">{{ lastDataAt(s.end_time) }}</td>
              <td class="r">{{ s.indices }}</td>
              <td class="fit">
                <UiButton
                  v-if="canRestore"
                  variant="quiet"
                  :disabled="busy || s.state !== 'SUCCESS'"
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
  </SettingsCard>
</template>

<style scoped>
.snap-unconfigured {
  margin: 14px 0 8px;
  font-size: var(--text-body);
  color: var(--soft);
}
/* flush under the preceding row's hairline, flush to the card foot (the data-panel grammar) */
.snap-wrap {
  margin: 0 -16px -14px;
  border: 0;
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
</style>
