<script setup lang="ts">
/**
 * The contributors lens — the shared strip grammar pointed at HANDLED findings (M9d slice 3):
 * the `/contributors` read's own `handled_over_time` daily histogram (settling actions:
 * resolve / not affected / risk accept / acknowledge), so the strip and the board below can
 * never disagree — one response, no second fetch. Props-fed; the view owns the settled
 * contract (lens ruling, issue 355: no claim before evidence). Clicking a bucket rewinds the whole app to that
 * bucket's end (D28), same as every lens.
 */
import { computed } from 'vue'

import { buildAuditLensOption, type ActivityPoint } from '@/charts/buildAuditLensOption'
import { bucketEndT } from '@/charts/buildIngestLensOption'
import EChart from '@/components/charts/EChart.vue'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { lastDataAt } from '@/system/freshness'

const props = defineProps<{
  series: ActivityPoint[]
  settled: boolean
  failed: boolean
}>()
const timeTravel = useTimeTravelStore()

const totalHandled = computed(() => props.series.reduce((n, p) => n + p.count, 0))
const option = computed(() => buildAuditLensOption(props.series, 'day', 'handled'))
const quiet = computed(() => props.settled && !props.failed && totalHandled.value === 0)

function onPointClick(params: { dataIndex: number }) {
  const bucket = props.series[params.dataIndex]?.date
  if (!bucket) return
  const t = bucketEndT(bucket, Date.now(), 'day')
  if (t === null) {
    timeTravel.backToNow()
    return
  }
  timeTravel.rewindTo(t)
  timeTravel.setWindow(timeTravel.windowDays, `→ ${lastDataAt(t)}`)
}
</script>

<template>
  <section class="ingest-lens" :class="{ 'il-quiet': quiet }" aria-label="Handled findings">
    <div class="il-head">
      <h3 class="il-title">Handled findings</h3>
      <span class="il-sub"
        >settling actions per day · {{ timeTravel.windowLabel.toLowerCase() }} · resolved ·
        not affected · risk accepted · acknowledged</span
      >
    </div>
    <div v-if="!settled" class="il-skel" aria-busy="true" aria-label="Loading handled findings" />
    <p v-else-if="failed" class="il-empty">Handled-findings activity unavailable.</p>
    <p v-else-if="totalHandled === 0" class="il-empty">
      No findings were handled in this window — the board below is empty too.
    </p>
    <div v-else title="Click a bucket to view the whole app as of its end">
      <EChart :option="option" :height="84" @point-click="onPointClick" />
    </div>
  </section>
</template>

<style scoped>
/* the ingest lens's card grammar verbatim — one strip language for every lens */
.ingest-lens {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 10px 14px 4px;
}
.il-quiet {
  background: var(--hist-bg);
  border-color: var(--hist-line);
}
.il-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 2px;
}
.il-title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink);
}
.il-sub {
  font-size: var(--text-control);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.il-empty {
  margin: auto 0;
  padding-bottom: 6px;
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--ink);
}
/* pre-data: a shimmer where the chart will be — never the amber claim (issue 355) */
.il-skel {
  height: 84px;
  margin-bottom: 6px;
  border-radius: var(--r-sm);
  background: linear-gradient(90deg, var(--line2) 25%, var(--panel) 50%, var(--line2) 75%);
  background-size: 200% 100%;
  animation: il-shimmer 1.4s ease-in-out infinite;
}
@keyframes il-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .il-skel {
    animation: none;
  }
}
</style>
