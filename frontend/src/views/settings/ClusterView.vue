<script setup lang="ts">
/**
 * Cluster panel (§13.8; prototype screens-config.jsx `cluster` section): identity & ingest
 * contract for the SELECTED cluster. `cluster_id` is immutable (the tenant key — never a query
 * key is the NAME's rule, the id routes indices); `cluster_name` is the relabelable display
 * name (D-5 registry, M8c) — the rename is journaled. Ruled prototype deltas (row 9):
 * `schema_version` displays 4 (prototype said 3); the ingest endpoint shows THIS deployment's
 * real path, not a lorem host.
 */
import { computed, ref, watch } from 'vue'

import { renameClusterApiV1ClustersClusterIdNamePut } from '@/api/generated'
import { client } from '@/api/client'
import SaveBar from '@/components/settings/SaveBar.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import SettingsRow from '@/components/settings/SettingsRow.vue'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'

// the envelope contract version this backend accepts (D44 schema v3 → v4 joint stamp; the
// ruled §13.8 display value — bump alongside the ingest contract)
const SCHEMA_VERSION = 4

const clusterStore = useClusterStore()
const toast = useToastStore()

const draft = ref('')
watch(
  () => clusterStore.selected?.cluster_name,
  (name) => {
    draft.value = name ?? ''
  },
  { immediate: true },
)

const dirty = computed(
  () => draft.value.trim() !== (clusterStore.selected?.cluster_name ?? '') && draft.value.trim() !== '',
)
const invalid = computed(() => draft.value.trim().length === 0 || draft.value.trim().length > 128)

const busy = ref(false)

async function save() {
  const id = clusterStore.selectedId
  if (!id || invalid.value) return
  busy.value = true
  const { response } = await renameClusterApiV1ClustersClusterIdNamePut({
    client,
    path: { cluster_id: id },
    body: { cluster_name: draft.value.trim() },
  })
  busy.value = false
  if (!response?.ok) {
    logger.warn('cluster_rename_failed', { status: response?.status })
    toast.error(
      response?.status === 503
        ? 'The registry is contended — try again.'
        : 'Renaming failed — the cluster keeps its current name.',
    )
    return
  }
  toast.success('Cluster renamed — display only, queries still key on the immutable id')
  await clusterStore.fetchClusters()
}

function discard() {
  draft.value = clusterStore.selected?.cluster_name ?? ''
}

const ingestEndpoint = computed(() => `${window.location.origin}/api/v1/ingest/scan`)
</script>

<template>
  <div>
    <SettingsCard title="Cluster" subtitle="identity & ingest contract">
      <SettingsRow label="cluster_id" hint="The immutable tenant key — indices and every query route on it." stack>
        <div class="static-row">
          <span class="static-value mono-sm">{{ clusterStore.selectedId ?? '—' }}</span>
          <span class="lock-tag">immutable</span>
        </div>
      </SettingsRow>
      <SettingsRow
        label="cluster_name"
        hint="Relabelable display name — never a query key. Renames are journaled."
        stack
      >
        <SettingsInput id="cluster-name" v-model="draft" :invalid="invalid && draft !== ''" />
      </SettingsRow>
      <SettingsRow label="Ingest endpoint" hint="Scanners push signed envelopes here over HTTPS with their scoped token." stack>
        <span class="static-value mono-sm">{{ ingestEndpoint }}</span>
      </SettingsRow>
      <SettingsRow label="API version">
        <span class="static-value mono-sm">/v1</span>
      </SettingsRow>
      <SettingsRow label="schema_version" hint="The envelope contract version this backend accepts.">
        <span class="static-value mono-sm">{{ SCHEMA_VERSION }}</span>
      </SettingsRow>
    </SettingsCard>

    <SaveBar :dirty="dirty" :invalid="invalid" :busy="busy" @save="save" @discard="discard" />
  </div>
</template>

<style scoped>
.mono-sm {
  font-family: var(--font-mono);
  font-size: var(--text-mono-cell);
}
.static-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.static-value {
  display: inline-block;
  padding: 8px 11px;
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-sm);
  color: var(--ink);
  word-break: break-all;
}
.lock-tag {
  flex: none;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--soft);
  border: 1px solid var(--line);
  padding: 3px 8px;
  border-radius: 5px;
}
</style>
