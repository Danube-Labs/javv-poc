<script setup lang="ts">
/**
 * The Overview KPI + signal bands (issue 384 split — extracted from OverviewView, no behavior
 * change). Joined hairline-divided stat grammar (base.css owns the skin, issue 368); every
 * number is a server aggregation read through the scanner lens; every cell click-throughs to
 * the findings grid.
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import AppIcon from '@/components/ui/AppIcon.vue'
import { useOverviewStore } from '@/stores/overview'
import { CHART_SEV, type Severity } from '@/styles/tokens'
import { countOf, fmt, type ScannerLens } from '@/views/overviewLens'

const KPI_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low']

const props = defineProps<{ scanner: ScannerLens }>()

const router = useRouter()
const overview = useOverviewStore()

const count = (facet: string, key: string) => countOf(overview.bucket(facet, key), props.scanner)
const sevCount = (s: Severity) => count('severity', s)
const totalPresent = computed(() => count('present', 'true'))
const fixableCount = computed(() => count('fixable', 'true'))
const fixPct = computed(() =>
  totalPresent.value === 0 ? 0 : Math.round((fixableCount.value / totalPresent.value) * 100),
)

/* 1b quick views — all straight facet reads */
const kevCount = computed(() => count('kev', 'true'))
const disagreeCount = computed(() => count('disagree', 'true'))
const stateCount = (k: string) => count('state', k)
const handledCount = computed(
  () => stateCount('resolved') + stateCount('not_affected') + stateCount('risk_accepted'),
)
const triage = computed(() => {
  const open = stateCount('open')
  const ack = stateCount('acknowledged')
  const stale = stateCount('stale')
  const handled = handledCount.value
  const total = open + ack + stale + handled
  const pct = (n: number) => (total === 0 ? 0 : (n / total) * 100)
  return { open, ack, stale, handled, total, pct }
})

function goFindings(query: Record<string, string>) {
  void router.push({ path: '/findings', query })
}
</script>

<template>
  <!-- KPI band: joined, hairline-divided (Nuxt stat grammar on our tokens) -->
  <div class="stat-band">
    <button
      v-for="s in KPI_SEVERITIES"
      :key="s"
      class="stat-cell"
      :title="`Open findings filtered to ${s}`"
      @click="goFindings({ severity: s })"
    >
      <span class="stat-label"><i class="stat-dot" :style="{ background: CHART_SEV[s] }" />{{ s }}<AppIcon class="cell-go" name="chevron" :size="11" /></span>
      <span class="stat-num">{{ fmt(sevCount(s)) }}</span>
    </button>
    <button class="stat-cell" title="Open findings with a fix available" @click="goFindings({ attr: 'fixable' })">
      <span class="stat-label"><i class="stat-dot" style="background: var(--teal)" />fix available<AppIcon class="cell-go" name="chevron" :size="11" /></span>
      <span class="stat-num">{{ fixPct }}%</span>
      <span class="stat-sub">{{ fmt(fixableCount) }} findings patchable today</span>
    </button>
  </div>

  <!-- signal band (1b): urgency + quality quick views, same joined grammar -->
  <div class="stat-band signal-band">
    <button class="stat-cell" title="Open known-exploited findings" @click="goFindings({ attr: 'kev' })">
      <span class="stat-label"><i class="stat-dot" style="background: var(--kev-bg)" />KEV · known-exploited<AppIcon class="cell-go" name="chevron" :size="11" /></span>
      <span class="stat-num" :class="{ 'stat-num--alarm': kevCount > 0 }">{{ fmt(kevCount) }}</span>
    </button>
    <button class="stat-cell" title="Open findings where the scanners disagree" @click="goFindings({ attr: 'disagree' })">
      <span class="stat-label"><i class="stat-dot" style="background: var(--sev-medium-solid)" />scanners disagree<AppIcon class="cell-go" name="chevron" :size="11" /></span>
      <span class="stat-num">{{ fmt(disagreeCount) }}</span>
    </button>
    <button class="stat-cell" title="Open the untriaged queue" @click="goFindings({ state: 'open' })">
      <span class="stat-label"><i class="stat-dot" style="background: var(--state-resolved-fg)" />triage progress<AppIcon class="cell-go" name="chevron" :size="11" /></span>
      <span class="stat-num">{{ triage.total === 0 ? '—' : `${Math.round(triage.pct(triage.handled + triage.ack))}%` }}</span>
      <span class="progress-bar" aria-hidden="true">
        <i class="seg-open" :style="{ width: `${triage.pct(triage.open)}%` }" />
        <i class="seg-ack" :style="{ width: `${triage.pct(triage.ack)}%` }" />
        <i class="seg-handled" :style="{ width: `${triage.pct(triage.handled)}%` }" />
        <i class="seg-stale" :style="{ width: `${triage.pct(triage.stale)}%` }" />
      </span>
      <span class="stat-sub">{{ fmt(triage.open) }} open · {{ fmt(triage.ack) }} ack · {{ fmt(triage.handled) }} handled<template v-if="triage.stale"> · {{ fmt(triage.stale) }} stale</template></span>
    </button>
  </div>
</template>

<style scoped>
/* the joined stat-band SKIN lives in base.css (issue 368) — only this screen's layout here */
.stat-band {
  grid-template-columns: repeat(5, 1fr);
}
.signal-band {
  grid-template-columns: repeat(3, 1fr);
  margin-top: 12px;
}

.progress-bar {
  display: flex;
  width: 100%;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  margin-top: 8px;
  background: var(--line2);
}
.progress-bar i {
  height: 100%;
}
.seg-open {
  background: var(--state-open-fg);
}
.seg-ack {
  background: var(--state-ack-fg);
}
.seg-handled {
  background: var(--state-resolved-fg);
}
.seg-stale {
  background: var(--state-stale-line);
}
@media (max-width: 1120px) {
  .stat-band {
    grid-template-columns: repeat(2, 1fr);
  }
  .stat-cell + .stat-cell {
    border-left: none;
  }
}
</style>
