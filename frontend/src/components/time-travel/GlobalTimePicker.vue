<script setup lang="ts">
/**
 * The whole-app rewind control (D28/FR-23, C-1): two visibly distinct controls in one group —
 * the time-travel T (Now / rewind presets / jump-to-date) and the trend window (relative to T).
 * Emits through the timeTravel store; the amber "viewing history" banner lives in AppShell.
 */
import { computed, ref } from 'vue'

import { useTimeTravelStore } from '@/stores/timeTravel'

const timeTravel = useTimeTravelStore()
const showJump = ref(false)
const jumpValue = ref('')

const REWINDS = [
  { label: '1h ago', seconds: 3600 },
  { label: '1d ago', seconds: 86400 },
  { label: '7d ago', seconds: 7 * 86400 },
] as const
const WINDOWS = [7, 30, 90] as const

const tLabel = computed(() =>
  timeTravel.isNow ? 'Now' : new Date(timeTravel.t as string).toLocaleString(),
)

function rewindBy(seconds: number) {
  timeTravel.rewindTo(new Date(Date.now() - seconds * 1000).toISOString())
  showJump.value = false
}

function jump() {
  if (!jumpValue.value) return
  timeTravel.rewindTo(new Date(jumpValue.value).toISOString())
  showJump.value = false
}
</script>

<template>
  <div class="picker" role="group" aria-label="Time travel">
    <span class="label">viewing</span>
    <button class="t-value" :class="{ past: !timeTravel.isNow }" @click="showJump = !showJump">
      <i class="pi pi-history" aria-hidden="true" /> {{ tLabel }}
    </button>
    <div v-if="showJump" class="menu">
      <button v-for="r in REWINDS" :key="r.label" class="item" @click="rewindBy(r.seconds)">
        {{ r.label }}
      </button>
      <div class="jump">
        <input v-model="jumpValue" type="datetime-local" aria-label="Jump to date" />
        <button class="item" @click="jump">Go</button>
      </div>
      <button v-if="!timeTravel.isNow" class="item now" @click="timeTravel.backToNow(); showJump = false">
        Back to now
      </button>
    </div>
    <span class="label sep">window</span>
    <select
      :value="timeTravel.windowDays"
      aria-label="Trend window"
      @change="timeTravel.setWindow(Number(($event.target as HTMLSelectElement).value))"
    >
      <option v-for="w in WINDOWS" :key="w" :value="w">{{ w }}d</option>
    </select>
  </div>
</template>

<style scoped>
.picker {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
}
.label {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--soft);
}
.sep {
  margin-left: 8px;
}
.t-value {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--card);
  color: var(--ink);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  cursor: pointer;
}
.t-value.past {
  border-color: var(--amber);
  background: var(--state-open-bg);
}
.menu {
  position: absolute;
  top: 110%;
  left: 0;
  z-index: 30;
  min-width: 220px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  box-shadow: var(--shadow);
}
.item {
  text-align: left;
  padding: 6px 8px;
  border: none;
  border-radius: var(--r-chip);
  background: none;
  color: var(--ink);
  font-size: var(--text-body);
  cursor: pointer;
}
.item:hover {
  background: var(--row-hover);
}
.item.now {
  color: var(--coral);
  font-weight: 600;
}
.jump {
  display: flex;
  gap: 4px;
  padding: 4px 8px;
}
.jump input {
  flex: 1;
  border: 1px solid var(--line);
  border-radius: var(--r-chip);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  padding: 3px 6px;
}
select {
  padding: 5px 8px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--card);
  color: var(--ink);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}
</style>
