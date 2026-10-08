<script setup lang="ts">
/**
 * The retirement countdown (issue 765): shown for the selected cluster only inside its last
 * `warn_days` before automatic retirement, from the schedule the cluster listing already carries
 * (`warns_at`, `retires_at`, `last_scan_at`). The health ramp: amber while there is time, red on
 * the last day and once past its date. Its own line under the freshness banner, and the fleet
 * table's countdown is a chip under the cluster's name: both ruled on built A/B specimens
 * (2026-10-07) over a sentence inside the freshness banner and a Retires in column.
 */
import { computed, onUnmounted, ref } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import { useClusterStore } from '@/stores/cluster'
import { isUrgent, retirementCountdown, retirementStatus, silenceClause } from '@/system/retirement'

// a pinned tab re-reads the list (a scan or the sweep moves the schedule) and the clock, on the
// freshness banner's cadence
const TICK_MS = 10 * 60_000

const clusterStore = useClusterStore()
const now = ref(Date.now())
const timer = setInterval(() => {
  now.value = Date.now()
  void clusterStore.refresh()
}, TICK_MS)
onUnmounted(() => clearInterval(timer))

const status = computed(() => {
  const row = clusterStore.selected
  return row ? retirementStatus(row, now.value) : null
})
const alone = computed(() => clusterStore.clusters.length === 1)
const silence = computed(() => (status.value ? silenceClause(status.value) : null))
const countdown = computed(() => (status.value ? retirementCountdown(status.value, alone.value) : null))
const urgent = computed(() => (status.value ? isUrgent(status.value, alone.value) : false))
</script>

<template>
  <Transition name="t-fade">
    <div
      v-if="silence"
      class="retire-line sys-line"
      :class="urgent ? 'tone-down' : 'tone-degraded'"
      :role="urgent ? 'alert' : 'status'"
    >
      <AppIcon class="sys-icon" name="alert" :size="15" />
      <span
        ><strong class="mono">{{ clusterStore.selected?.cluster_name }}</strong> {{ silence }} {{ countdown }}</span
      >
    </div>
  </Transition>
</template>
