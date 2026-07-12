<script setup lang="ts">
/**
 * Top-contributor podium card (M9d slice 3; prototype `PodiumCard`, structure-only onto
 * tokens). Trimmed to the wire's truth: resolved count + SLA / median meta — no severity mix,
 * roles, or streaks (not on the wire; backlogged). Rank 1 gets the coral badge + emphasis
 * border, never a fabricated gradient.
 */
import { computed } from 'vue'

import ContributorIdentity from '@/components/contributors/ContributorIdentity.vue'
import { fmtMedian, resolvedOf, type BoardRow } from '@/contributors/viewModel'

const props = defineProps<{ row: BoardRow; rank: 1 | 2 | 3 }>()

const fmt = (n: number) => n.toLocaleString('en-US')
const resolved = computed(() => resolvedOf(props.row))
const sla = computed(() =>
  props.row.sla_hit_pct === null ? '—' : `${Math.round(props.row.sla_hit_pct)}%`,
)
</script>

<template>
  <div class="podium" :class="{ 'podium-first': rank === 1 }">
    <div class="podium-rank" aria-hidden="true">{{ rank }}</div>
    <ContributorIdentity :actor="row.actor" :size="rank === 1 ? 56 : 46" vertical />
    <div class="podium-num">
      {{ fmt(resolved) }}<em>resolved</em>
    </div>
    <div class="podium-meta">
      <span><b>{{ sla }}</b> SLA</span>
      <span><b>{{ fmtMedian(row.median_ttr_seconds) }}</b> median</span>
    </div>
  </div>
</template>

<style scoped>
/* prototype .podium family on tokens; rank-1 emphasis = coral badge + line, no gradients */
.podium {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  border: 1px solid var(--line);
  border-radius: var(--r);
  padding: 18px 14px 16px;
  background: var(--panel);
  position: relative;
}
.podium-first {
  border-color: var(--coral);
  padding-top: 24px;
  box-shadow: var(--shadow);
}
.podium-rank {
  position: absolute;
  top: -11px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--slate);
  color: var(--side-brand-fg);
  display: grid;
  place-items: center;
  font-size: var(--text-sm);
  font-weight: 700;
  font-family: var(--font-mono);
}
.podium-first .podium-rank {
  background: var(--coral);
  width: 28px;
  height: 28px;
  top: -13px;
}
/* the stat grammar — numbers are mono/700 ink app-wide */
.podium-num {
  font-family: var(--font-mono);
  font-size: var(--text-stat);
  font-weight: 700;
  color: var(--ink);
  margin-top: 10px;
}
.podium-num em {
  font-style: normal;
  display: block;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--ink);
  margin-top: 2px;
}
.podium-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 5px 12px;
  font-size: var(--text-sm);
  color: var(--soft);
  margin-top: 10px;
}
.podium-meta span {
  white-space: nowrap;
}
.podium-meta b {
  color: var(--ink);
  font-family: var(--font-mono);
}
</style>
