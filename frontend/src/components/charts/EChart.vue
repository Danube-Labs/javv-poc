<script setup lang="ts">
/**
 * THE chart shell: vue-echarts with MANUAL module registration (never the full echarts
 * bundle — day-one FE rule) and the markRaw/shallow hygiene in one place. Consumers pass a
 * pure-built option (charts/build*.ts) and a height; everything else is owned here.
 */
import { markRaw, shallowRef, watchEffect } from 'vue'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import VChart from 'vue-echarts'

use([LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{ option: EChartsOption; height?: number }>()
const emit = defineEmits<{ 'point-click': [params: { dataIndex: number; seriesName?: string }] }>()

const raw = shallowRef(markRaw(props.option))
watchEffect(() => {
  raw.value = markRaw(props.option)
})
</script>

<template>
  <VChart
    :option="raw"
    :style="{ height: `${height ?? 250}px` }"
    autoresize
    @click="emit('point-click', $event as { dataIndex: number; seriesName?: string })"
  />
</template>
