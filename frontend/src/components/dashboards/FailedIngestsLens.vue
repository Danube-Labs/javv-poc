<script setup lang="ts">
/**
 * The failed-ingests lens: pushes the backend refused after checking their token, per bucket,
 * one bar series per scanner (never merged) — `GET /trends/ingest-failures`. Built to sit under
 * the Scan ingest strip on the same axis: the same window, the same day/hour bucket rule, so a day
 * lines up across both. Its own scale on purpose: runs peak in the hundreds while refusals are a
 * handful, so bars sharing Scan ingest's axis would vanish (issue 575).
 *
 * Self-contained per DESIGN.md section 10 — `(clusterId, t, windowDays)` in, its own fetch and
 * loading/empty/error states. A click on a day rewinds the whole app, like Scan ingest.
 */
import { computed, ref, watch } from 'vue'

import { client } from '@/api/client'
import { ingestFailuresTrendApiV1TrendsIngestFailuresGet } from '@/api/generated'
import {
  buildIngestLensOption,
  ingestInterval,
  ingestLensDates,
} from '@/charts/buildIngestLensOption'
import { buildTrendQuery } from '@/charts/buildTrendQuery'
import EChart from '@/components/charts/EChart.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useBucketRewind } from '@/composables/useBucketRewind'
import { logger } from '@/lib/logger'
import {
  failuresAsLensSeries,
  totalRefused,
  type IngestFailuresTrend,
} from '@/system/ingestFailures'

const props = defineProps<{
  clusterId: string
  /** the rewound T, `null` = now */
  t: string | null
  windowDays: number
}>()

const series = ref<IngestFailuresTrend>({})
const failed = ref(false)
// no claim before evidence: "no refused pushes" only once an answer has landed
const settled = ref(false)

const interval = computed(() => ingestInterval(props.windowDays, props.t))

watch(
  () => [props.clusterId, props.t, props.windowDays] as const,
  async ([id, t, days], old) => {
    if (old && old[0] !== id) {
      settled.value = false // another tenant's bars would be a lie
      series.value = {}
    }
    const { data, response } = await ingestFailuresTrendApiV1TrendsIngestFailuresGet({
      client,
      query: { ...buildTrendQuery(id, days, t), interval: interval.value } as never,
    })
    failed.value = !response?.ok
    if (failed.value) logger.warn('failed_ingests_lens_failed', { status: response?.status })
    series.value = response?.ok ? ((data as { series: IngestFailuresTrend }).series ?? {}) : {}
    settled.value = true
  },
  { immediate: true },
)

const lensSeries = computed(() => failuresAsLensSeries(series.value))
const refused = computed(() => totalRefused(series.value))
const option = computed(() => buildIngestLensOption(lensSeries.value, interval.value))

const rewindToBucket = useBucketRewind()
function onPointClick(params: { dataIndex: number }) {
  rewindToBucket(ingestLensDates(lensSeries.value)[params.dataIndex], interval.value)
}
</script>

<template>
  <section class="fail-lens" aria-label="Failed ingest activity">
    <div class="fl-head">
      <h3 class="fl-title">Failed ingests</h3>
      <span class="fl-sub">pushes the backend refused per {{ interval }}</span>
      <span v-if="settled && !failed && refused > 0" class="fl-total mono-cell"
        >{{ refused }} in this range</span
      >
    </div>
    <UiSkeleton v-if="!settled" :height="56" radius="sm" label="Loading failed ingests" class="skel-gap" />
    <p v-else-if="failed" class="fl-empty">Failed-ingest activity unavailable.</p>
    <p v-else-if="refused === 0" class="fl-empty">No refused pushes in this range.</p>
    <div v-else title="Click a day to view the whole app as of the end of that day">
      <EChart :option="option" :height="56" @point-click="onPointClick" />
    </div>
  </section>
</template>

<style scoped>
/* the ingest strip's card skin, so the lens stands on its own on any host */
.fail-lens {
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 10px 14px 4px;
}
.fl-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 2px;
}
.fl-title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink);
}
.fl-sub {
  font-size: var(--text-control);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.fl-total {
  margin-left: auto;
  font-size: var(--text-control);
  color: var(--ink);
}
.fl-empty {
  margin: 0;
  padding-bottom: 6px;
  font-size: var(--text-body);
  color: var(--ink);
}
.skel-gap {
  margin-bottom: 6px;
}
</style>
