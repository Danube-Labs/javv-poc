<script setup lang="ts">
/**
 * POC (operator option D, 2026-07-09): ONE Kibana-style time-RANGE control replacing the
 * two-section time-travel/trend-window menu. A range maps exactly onto the shipped backend:
 * the END of the range is the whole-app `as_of` T (D28 — `null` when the range ends now), the
 * SPAN is `days` for the M9c trend charts (int 1–365). One mental model, honest copy:
 * tables show state at the END of the range; charts aggregate the whole span.
 * The button goes amber (`--hist-*`) whenever the range ends in the past.
 */
import { computed, onMounted, onUnmounted, ref, useTemplateRef } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import { useTimeTravelStore } from '@/stores/timeTravel'

const timeTravel = useTimeTravelStore()
const open = ref(false)
const relN = ref(30)
const relUnit = ref<'minutes' | 'hours' | 'days' | 'weeks'>('days')
const fromDate = ref('')
const fromTime = ref('00:00')
const toDate = ref('')
const toTime = ref('')
const wrap = useTemplateRef<HTMLElement>('wrap')

const UNIT_MS = { minutes: 60_000, hours: 3_600_000, days: 86_400_000, weeks: 604_800_000 } as const
const TIME_RE = /^([01]?\d|2[0-3]):[0-5]\d$/ // strict 24h HH:mm — no AM/PM anywhere

/* quick ranges, all ending now — the trends contract is whole days 1..365 */
const PRESETS: readonly [string, number][] = [
  ['Last 24 hours', 1],
  ['Last 7 days', 7],
  ['Last 30 days', 30],
  ['Last 90 days', 90],
  ['Last 180 days', 180],
  ['Last 1 year', 365],
]

const DAY_MS = 86_400_000

const buttonLabel = computed(() => timeTravel.windowLabel)

function applyPreset(label: string, days: number) {
  timeTravel.backToNow()
  timeTravel.setWindow(days, label)
  open.value = false
}

function applyRelative() {
  if (!relN.value || relN.value < 1) return
  // charts take whole days (trends contract int 1..365) — sub-day spans round up to 1 day
  // for the days param; the label keeps the user's exact choice
  const days = Math.min(365, Math.max(1, Math.ceil((relN.value * UNIT_MS[relUnit.value]) / DAY_MS)))
  const unit = relUnit.value.slice(0, -1)
  timeTravel.backToNow()
  timeTravel.setWindow(days, `Last ${relN.value} ${unit}${relN.value === 1 ? '' : 's'}`)
  open.value = false
}

/* 24-hour display everywhere — never AM/PM */
const fmtD = (d: Date) =>
  d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

const parseSide = (date: string, time: string): Date | null => {
  if (!date || !TIME_RE.test(time)) return null
  return new Date(`${date}T${time.padStart(5, '0')}:00`)
}

const customValid = computed(() => {
  const from = parseSide(fromDate.value, fromTime.value)
  const to = parseSide(toDate.value, toTime.value)
  return from !== null && to !== null && from.getTime() < to.getTime()
})

function applyCustom() {
  const from = parseSide(fromDate.value, fromTime.value)
  const to = parseSide(toDate.value, toTime.value)
  if (!from || !to || from.getTime() >= to.getTime()) return
  // charts take whole days (trends contract int 1..365); the END is minute-precise as_of
  const span = Math.min(365, Math.max(1, Math.round((to.getTime() - from.getTime()) / DAY_MS) || 1))
  const label = `${fmtD(from)} → ${fmtD(to)}`
  if (to.getTime() >= Date.now() - 60_000) {
    timeTravel.backToNow() // range ends now-ish: tables show current state
  } else {
    timeTravel.rewindTo(to.toISOString()) // past end: tables show as-scanned at that minute
  }
  timeTravel.setWindow(span, label)
  open.value = false
}

function backToNow() {
  timeTravel.backToNow()
  timeTravel.setWindow(30, 'Last 30 days')
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
      aria-label="Time range"
      @click="open = !open"
    >
      <AppIcon :name="timeTravel.isNow ? 'calendar' : 'rewind'" :size="14" />
      {{ buttonLabel }}
      <AppIcon name="chevron" :size="13" />
    </button>

    <div v-if="open" class="dd-menu time-menu">
      <div class="tt-note">
        One range drives the whole app: <b>tables show state at the end of the range</b> (a past
        end = as-scanned history) · charts aggregate the span.
      </div>

      <div class="dd-head">Quick select</div>
      <div class="time-rel">
        <span class="time-rel-label">Last</span>
        <input
          v-model.number="relN"
          class="num-input mono-cell"
          type="number"
          min="1"
          max="365"
          aria-label="Range length"
        />
        <select v-model="relUnit" class="select-input" aria-label="Range unit">
          <option value="minutes">minutes</option>
          <option value="hours">hours</option>
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
          :class="{ 'time-preset-on': timeTravel.isNow && timeTravel.windowLabel === p }"
          @click="applyPreset(p, days)"
        >
          {{ p }}
        </button>
      </div>

      <div class="dd-head">Absolute range (24h)</div>
      <div class="time-abs">
        <input v-model="fromDate" class="text-input mono-cell" type="date" aria-label="Range start date" />
        <input
          v-model="fromTime"
          class="text-input mono-cell hhmm"
          type="text"
          placeholder="HH:mm"
          maxlength="5"
          aria-label="Range start time (24h)"
        />
        <span class="time-arrow">→</span>
        <input v-model="toDate" class="text-input mono-cell" type="date" aria-label="Range end date" />
        <input
          v-model="toTime"
          class="text-input mono-cell hhmm"
          type="text"
          placeholder="HH:mm"
          maxlength="5"
          aria-label="Range end time (24h)"
        />
        <button class="btn-mini time-apply" :disabled="!customValid" @click="applyCustom">Apply</button>
      </div>

      <button v-if="!timeTravel.isNow" class="back-now" @click="backToNow">
        <AppIcon name="rewind" :size="13" /> Back to now (Last 30 days)
      </button>
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
  color: var(--ink); /* primary control text — never washy soft-on-panel */
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
.tt-note {
  font-size: var(--text-sm);
  color: var(--ink);
  padding: 8px 10px;
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
  color: var(--ink);
}
.time-apply {
  margin-left: auto;
}
.btn-mini {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: var(--text-quiet-action);
  font-weight: 600;
  padding: 5px 9px;
  background: var(--panel);
  border: 1px solid var(--line);
  color: var(--ink);
  border-radius: 7px;
  cursor: pointer;
}
.btn-mini:hover {
  border-color: var(--control-hover-line);
}
.btn-mini:disabled {
  opacity: 0.45;
  cursor: default;
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
.time-arrow {
  color: var(--soft);
  flex: none;
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
.hhmm {
  width: 62px;
  text-align: center;
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
.back-now {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  border: 0;
  border-top: 1px solid var(--line2);
  background: transparent;
  color: var(--coral-d);
  font-size: var(--text-control);
  font-weight: 600;
  padding: 9px 10px 7px;
  margin-top: 4px;
  cursor: pointer;
}
.back-now:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
</style>
