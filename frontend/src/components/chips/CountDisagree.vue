<script setup lang="ts">
/** Per-image count-disagreement pair (prototype `CountDisagree`, D5b): each scanner's finding
 * count under its OWN colored letter chip — never summed — with the delta as an amber badge.
 * Agreement (or a single scanner) renders the plain count; the tooltip spells the pair out
 * for first readers. */
import { computed } from 'vue'

const props = defineProps<{
  trivy?: number | null
  grype?: number | null
  total: number
}>()

const delta = computed(() =>
  props.trivy != null && props.grype != null ? props.trivy - props.grype : null,
)
const fmt = (n: number) => n.toLocaleString('en-US')
const title = computed(() =>
  delta.value === null
    ? 'One scanner has scanned this digest so far'
    : delta.value === 0
      ? 'Trivy and Grype report the same count'
      : `Trivy found ${fmt(props.trivy!)}, Grype found ${fmt(props.grype!)} — Δ ${delta.value > 0 ? '+' : ''}${fmt(delta.value)}. Counts are never summed.`,
)
</script>

<template>
  <span v-if="delta === null || delta === 0" class="cd-agree" :title="title">{{ fmt(total) }}</span>
  <span v-else class="cd-split" :title="title">
    <span class="cd-t"><i>T</i>{{ fmt(trivy!) }}</span>
    <span class="cd-g"><i>G</i>{{ fmt(grype!) }}</span>
    <span class="cd-delta">Δ {{ delta > 0 ? '+' : '' }}{{ fmt(delta) }}</span>
  </span>
</template>

<style scoped>
.cd-agree {
  font-family: var(--font-mono);
  font-weight: 600;
}
.cd-split {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  white-space: nowrap;
}
.cd-t,
.cd-g {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-weight: 600;
}
.cd-split i {
  font-style: normal;
  font-size: var(--text-chip-sm);
  font-weight: 700;
  width: 14px;
  height: 14px;
  border-radius: 3px;
  display: inline-grid;
  place-items: center;
}
.cd-t i {
  background: var(--scanner-trivy-bg);
  color: var(--scanner-trivy-fg);
}
.cd-g i {
  background: var(--scanner-grype-bg);
  color: var(--scanner-grype-fg);
}
.cd-delta {
  font-size: var(--text-chip-sm);
  font-weight: 700;
  color: var(--health-degraded-fg);
  background: var(--health-degraded-bg);
  padding: 1px 5px;
  border-radius: 4px;
}
</style>
