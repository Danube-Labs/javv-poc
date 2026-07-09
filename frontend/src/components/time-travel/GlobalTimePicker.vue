<script setup lang="ts">
/**
 * Kibana-style global time control (prototype main.jsx `TimePicker` + `.time-*`/`.tt-*` CSS):
 * ONE `time-range` button opening a two-section menu —
 *   · time-travel (D28/FR-23): Now / quick rewinds / jump-to-date → the global `as_of` T; the
 *     button goes amber (`time-range-hist`) while viewing history;
 *   · trend window: Last-N + day presets → `windowDays` for the M9c dashboard charts (grids
 *     always show state at T; they take no window param).
 * Shipped-contract deviations from the prototype (bolt M9a README 2026-07-09): the trends
 * `days` param is an integer 1–365, so no minutes/hours window units and no absolute
 * from→to range (that becomes rewind-to+window when dashboards land).
 */
import { computed, onMounted, onUnmounted, ref, useTemplateRef } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import { useTimeTravelStore } from '@/stores/timeTravel'

const timeTravel = useTimeTravelStore()
const open = ref(false)
const jumpDate = ref('')
const relN = ref(30)
const relUnit = ref<'days' | 'weeks'>('days')
const wrap = useTemplateRef<HTMLElement>('wrap')

const REWINDS = [
  { label: '1 hour ago', seconds: 3600 },
  { label: '24 hours ago', seconds: 86400 },
  { label: '7 days ago', seconds: 7 * 86400 },
  { label: '30 days ago', seconds: 30 * 86400 },
] as const

/* whole-day presets only — the trends contract is days 1..365 */
const PRESETS: readonly [string, number][] = [
  ['Last 24 hours', 1],
  ['Last 7 days', 7],
  ['Last 30 days', 30],
  ['Last 90 days', 90],
  ['Last 180 days', 180],
  ['Last 1 year', 365],
]

const activeRewind = ref<string | null>(null)

const buttonLabel = computed(() =>
  timeTravel.isNow
    ? timeTravel.windowLabel
    : (activeRewind.value ?? `as scanned ${new Date(timeTravel.t as string).toLocaleDateString()}`),
)

function rewindBy(label: string, seconds: number) {
  timeTravel.rewindTo(new Date(Date.now() - seconds * 1000).toISOString())
  activeRewind.value = label
  open.value = false
}
function backToNow() {
  timeTravel.backToNow()
  activeRewind.value = null
  open.value = false
}
function jump() {
  if (!jumpDate.value) return
  timeTravel.rewindTo(new Date(jumpDate.value).toISOString())
  activeRewind.value = null
  open.value = false
}
function applyPreset(label: string, days: number) {
  timeTravel.setWindow(days, label)
  open.value = false
}
function applyRelative() {
  const days = Math.min(365, Math.max(1, relUnit.value === 'weeks' ? relN.value * 7 : relN.value))
  const unit = relUnit.value === 'weeks' ? 'week' : 'day'
  timeTravel.setWindow(days, `Last ${relN.value} ${unit}${relN.value === 1 ? '' : 's'}`)
  open.value = false
}

function onDocMousedown(e: MouseEvent) {
  if (wrap.value && !wrap.value.contains(e.target as Node)) open.value = false
}
onMounted(() => document.addEventListener('mousedown', onDocMousedown))
onUnmounted(() => document.removeEventListener('mousedown', onDocMousedown))
</script>

<template>
  <div ref="wrap" class="dropdown" @keydown.esc="open = false">
    <button
      class="time-range"
      :class="{ 'time-range-hist': !timeTravel.isNow }"
      aria-label="Time travel and trend window"
      @click="open = !open"
    >
      <AppIcon :name="timeTravel.isNow ? 'calendar' : 'rewind'" :size="14" />
      {{ buttonLabel }}
      <AppIcon name="chevron" :size="13" />
    </button>

    <div v-if="open" class="dd-menu time-menu">
      <div class="dd-head">Time-travel · rewind the whole app</div>
      <div class="time-travel">
        <button class="tt-opt" :class="{ 'tt-on': timeTravel.isNow }" @click="backToNow">Now</button>
        <button
          v-for="r in REWINDS"
          :key="r.label"
          class="tt-opt"
          :class="{ 'tt-on': activeRewind === r.label }"
          @click="rewindBy(r.label, r.seconds)"
        >
          {{ r.label }}
        </button>
      </div>
      <div class="time-abs">
        <input v-model="jumpDate" class="text-input mono-cell" type="date" aria-label="Jump to date" />
        <button class="btn-mini time-apply" @click="jump">Jump to date</button>
      </div>
      <div class="tt-note">
        At a past moment every screen shows <b>as-scanned</b> state — reach is bounded by each
        cluster's retained data.
      </div>

      <div class="dd-head">Trend window (dashboards)</div>
      <div class="time-rel">
        <span class="time-rel-label">Last</span>
        <input
          v-model.number="relN"
          class="num-input mono-cell"
          type="number"
          min="1"
          max="365"
          aria-label="Window length"
        />
        <select v-model="relUnit" class="select-input" aria-label="Window unit">
          <option value="days">days</option>
          <option value="weeks">weeks</option>
        </select>
        <button class="btn-mini time-apply" @click="applyRelative">Apply</button>
      </div>
      <div class="dd-head">Commonly used</div>
      <div class="time-presets">
        <button
          v-for="[p, days] in PRESETS"
          :key="p"
          class="time-preset"
          :class="{ 'time-preset-on': timeTravel.windowLabel === p }"
          @click="applyPreset(p, days)"
        >
          {{ p }}
        </button>
      </div>
      <div class="time-note">
        Drives the dashboard charts (M9c) — tables always show state at the selected moment.
      </div>
    </div>
  </div>
</template>

<style scoped>
.dropdown {
  position: relative;
}
.time-range {
  display: flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--line);
  border-radius: 9px;
  padding: 7px 11px;
  color: var(--soft);
  font-size: var(--text-dd-item);
  background: var(--panel);
  font-family: var(--font-ui);
  cursor: pointer;
}
.time-range:hover {
  border-color: var(--control-hover-line);
}
.time-range:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.time-range-hist {
  background: var(--hist-bg);
  border-color: var(--hist-line);
  color: var(--hist-fg);
}
.dd-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 30;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  box-shadow: var(--dd-shadow);
  padding: 6px;
}
.time-menu {
  min-width: 340px;
}
.dd-head {
  font-family: var(--font-mono);
  font-size: var(--text-dd-head);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--soft);
  padding: 8px 12px 6px;
}
.time-travel {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 2px 8px 8px;
}
.tt-opt {
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: 7px;
  padding: 5px 11px;
  font-size: var(--text-control);
  color: var(--soft);
  cursor: pointer;
}
.tt-opt:hover {
  border-color: var(--control-hover-line);
  color: var(--ink);
}
.tt-opt:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.tt-on {
  background: var(--coral);
  border-color: var(--coral);
  color: var(--kev-fg);
  font-weight: 600;
}
.tt-note {
  font-size: var(--text-facet-count);
  color: var(--soft);
  padding: 6px 8px 10px;
  line-height: 1.5;
  border-bottom: 1px solid var(--line2);
  margin-bottom: 4px;
}
.time-rel {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px 10px;
}
.time-rel-label {
  font-size: var(--text-control);
  color: var(--soft);
}
.time-apply {
  margin-left: auto;
}
.btn-mini {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: var(--text-quiet-action);
  padding: 5px 9px;
  background: var(--panel);
  border: 1px solid var(--line);
  color: var(--soft);
  border-radius: 7px;
  cursor: pointer;
}
.btn-mini:hover {
  border-color: var(--control-hover-line);
  color: var(--ink);
}
.btn-mini:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.time-presets {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3px;
  padding: 2px 8px 10px;
}
.time-preset {
  border: 0;
  background: transparent;
  text-align: left;
  padding: 6px 9px;
  border-radius: 7px;
  font-size: var(--text-control);
  color: var(--ink);
  cursor: pointer;
}
.time-preset:hover {
  background: var(--panel);
}
.time-preset-on {
  background: var(--dd-on-bg);
  color: var(--coral-d);
  font-weight: 600;
}
.time-abs {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 4px 10px 8px;
}
.text-input,
.num-input {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: var(--text-sm);
  color: var(--ink);
  background: var(--card);
  outline: none;
  font-family: inherit;
}
.num-input {
  width: 64px;
}
.text-input:focus,
.num-input:focus {
  border-color: var(--coral);
}
.select-input {
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: var(--text-control);
  color: var(--ink);
  outline: none;
  width: 96px;
}
.select-input:focus {
  border-color: var(--coral);
}
.mono-cell {
  font-family: var(--font-mono);
}
.time-note {
  font-family: var(--font-mono);
  font-size: var(--text-dd-head);
  color: var(--soft);
  padding: 8px 10px 6px;
  border-top: 1px solid var(--line2);
  line-height: 1.5;
}
</style>
