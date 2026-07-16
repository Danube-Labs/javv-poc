<script setup lang="ts">
/** Severity mix (prototype MiniBar + MixBar): proportional segments of ONE scanner's severity
 * buckets — never a cross-scanner merge — with the per-severity counts readable on hover
 * (title) and, with `numbers`, as a colored count row under the bar (tables). Attribution
 * (whose scan) rides the tooltip or the optional inline label. Zero total = muted dash. */
import { computed } from 'vue'

import { CHART_SEV, type Severity } from '@/styles/tokens'

const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'negligible', 'unknown']
const NUMBER_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low']

const props = defineProps<{
  counts: Partial<Record<Severity, number>>
  /** inline scanner label to the left of the bar (the all-clusters per-scanner stack) */
  label?: string
  /** colored per-severity counts under the bar (the prototype table treatment) */
  numbers?: boolean
  /** whose committed scan these buckets are — named in the tooltip */
  attribution?: string
}>()

const entries = computed(() => SEVERITIES.map((sev) => ({ sev, n: props.counts[sev] ?? 0 })))
const total = computed(() => entries.value.reduce((n, e) => n + e.n, 0))
const segments = computed(() =>
  total.value === 0
    ? null
    : entries.value
        .filter((e) => e.n > 0)
        .map((e) => ({ sev: e.sev, pct: (e.n / total.value) * 100, color: CHART_SEV[e.sev] })),
)
const fmt = (n: number) => n.toLocaleString('en-US')
const title = computed(() => {
  const parts = entries.value.filter((e) => e.n > 0).map((e) => `${e.sev} ${fmt(e.n)}`)
  const who = props.attribution ?? props.label
  return `${parts.length ? parts.join(' · ') : 'no findings'}${who ? ` — ${who}'s committed scan` : ''}`
})
</script>

<template>
  <div class="mix">
    <div class="mix-row">
      <span v-if="label" class="mix-scanner" :data-scanner="label.toLowerCase()">{{ label }}</span>
      <span v-if="segments || numbers" class="mix-bar" :title="title">
        <i v-for="seg in segments ?? []" :key="seg.sev" :style="{ width: `${seg.pct}%`, background: seg.color }" />
      </span>
      <span v-else class="muted-dash" :title="title">-</span>
    </div>
    <span v-if="numbers" class="mix-nums" :title="title">
      <b v-for="sev in NUMBER_SEVERITIES" :key="sev" :class="`mn-${sev}`">{{ fmt(counts[sev] ?? 0) }}</b>
    </span>
  </div>
</template>

<style scoped>
.mix-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.mix-scanner {
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  color: var(--soft);
  width: 38px;
  flex: none;
}
/* scanner identity (§8.5 specimen): the label wears its scanner's hue — same identity language
   as ScannerTag, no escalation */
.mix-scanner[data-scanner='trivy'] {
  color: var(--scanner-trivy-fg);
}
.mix-scanner[data-scanner='grype'] {
  color: var(--scanner-grype-fg);
}
.mix-bar {
  display: flex;
  flex: 1;
  min-width: 90px;
  height: 7px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--line2);
}
.mix-bar i {
  height: 100%;
}
.mix-nums {
  display: flex;
  gap: 10px;
  margin-top: 4px;
  font-family: var(--font-mono);
  font-size: var(--text-chip-sm);
  line-height: 1;
}
.mix-nums b {
  font-weight: 700;
}
.mn-critical {
  color: var(--sev-critical-fg);
}
.mn-high {
  color: var(--sev-high-fg);
}
.mn-medium {
  color: var(--sev-medium-fg);
}
.mn-low {
  color: var(--sev-low-fg);
}
.muted-dash {
  color: var(--dash-muted);
}
</style>
