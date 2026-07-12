<script setup lang="ts">
/**
 * Contributors screen (M9d slice 3; SCREENS-v5 §11, prototype screens-heroes.jsx trimmed to
 * the wire's truth): the shared data-screen band (head-card + the handled-findings lens — the
 * same strip grammar every data screen carries) over team KPIs → podium → leaderboard, with
 * the recent-activity feed alongside. ALL numbers are `GET /contributors`' (leaderboard +
 * `totals`, one response — pooled team median/SLA are server-computed, never client math);
 * the feed is the M8c audit read. Scoped by the global trend window (`days`) and rewindable
 * (D28: the endpoint reconstructs at a past `as_of` — no limitation notice here). Trimmed by
 * ruling: per-actor severity mix / pace / streaks / roles (not on the wire), the scan-observed
 * trends chart (not attributable to contributors, A-m9), CSV export (issue 359).
 */
import { computed, ref, watch } from 'vue'

import { contributorsApiV1ContributorsGet } from '@/api/generated'
import type { ContributorsApiV1ContributorsGetData } from '@/api/generated'
import type { ActivityPoint } from '@/charts/buildAuditLensOption'
import ActivityFeed from '@/components/contributors/ActivityFeed.vue'
import ContributorsLens from '@/components/contributors/ContributorsLens.vue'
import LeaderboardTable from '@/components/contributors/LeaderboardTable.vue'
import PodiumCard from '@/components/contributors/PodiumCard.vue'
import { useApi } from '@/composables/useApi'
import {
  daysFromWindow,
  fmtMedian,
  sortBoard,
  type BoardRow,
  type TeamTotals,
} from '@/contributors/viewModel'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'

const BOARD_CAP = 100 // the endpoint's terms-agg board size — the table labels the cap

const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const { withGlobals } = useApi()

const board = ref<BoardRow[]>([])
const totals = ref<TeamTotals | null>(null)
const handledSeries = ref<ActivityPoint[]>([])
const failed = ref(false)
const settled = ref(false)

const query = computed(() =>
  clusterStore.selectedId
    ? withGlobals({ days: daysFromWindow(timeTravel.windowDays) })
    : null,
)

watch(
  query,
  async (q, old) => {
    if (!q) return
    if (old && old.cluster_id !== q.cluster_id) {
      settled.value = false
      board.value = []
      totals.value = null
      handledSeries.value = []
    }
    const response = await contributorsApiV1ContributorsGet({
      query: q as ContributorsApiV1ContributorsGetData['query'],
    })
    failed.value = !response.response?.ok
    if (failed.value) {
      logger.warn('contributors_load_failed', { status: response.response?.status })
    } else {
      const body = response.data as unknown as {
        leaderboard: BoardRow[]
        handled_over_time: ActivityPoint[]
        totals: TeamTotals
      }
      board.value = body.leaderboard ?? []
      handledSeries.value = body.handled_over_time ?? []
      totals.value = body.totals ?? null
    }
    settled.value = true
  },
  { immediate: true, deep: true },
)

const podium = computed(() => {
  const top = sortBoard(board.value).slice(0, 3)
  // prototype visual order 2 · 1 · 3 — only when there are three to stage
  if (top.length === 3) return [
    { row: top[1]!, rank: 2 as const },
    { row: top[0]!, rank: 1 as const },
    { row: top[2]!, rank: 3 as const },
  ]
  return top.map((row, i) => ({ row, rank: (i + 1) as 1 | 2 | 3 }))
})

const fmt = (n: number) => n.toLocaleString('en-US')
const teamSla = computed(() =>
  totals.value?.sla_hit_pct == null ? '—' : `${Math.round(totals.value.sla_hit_pct)}%`,
)
const windowLabel = computed(() => timeTravel.windowLabel.toLowerCase())
</script>

<template>
  <div class="screen">
    <div class="screen-head screen-head-band">
      <div class="head-card">
        <h1>Contributors</h1>
        <p class="head-stat">
          {{ board.length }}<span class="head-unit"> contributors</span>
        </p>
        <p class="head-note">derived from the audit trail · triage actions, not scan deltas</p>
      </div>
      <ContributorsLens :series="handledSeries" :settled="settled" :failed="failed" />
    </div>

    <div v-if="!settled" class="contrib-skel" aria-busy="true" aria-label="Loading contributors">
      <div class="skel skel-band" />
      <div class="skel skel-card" />
    </div>

    <p v-else-if="failed" class="load-error" role="alert">
      Contributors unavailable. Check the backend connection.
    </p>

    <div v-else-if="board.length === 0" class="not-found" role="status">
      <p>No triage activity in this window — handled findings chart contributors here.</p>
    </div>

    <template v-else>
      <!-- team KPI band: the ruled joined hairline-divided stat grammar (Overview), fed by
           the server's totals block — pooled median/SLA are not client-derivable -->
      <div v-if="totals" class="kpi-band">
        <div class="kpi-cell">
          <span class="kpi-label"><i class="kpi-dot kpi-dot-resolved" />resolved</span>
          <span class="kpi-num">{{ fmt(totals.by_action['resolve'] ?? 0) }}</span>
          <span class="kpi-sub">{{ windowLabel }}</span>
        </div>
        <div class="kpi-cell">
          <span class="kpi-label"><i class="kpi-dot kpi-dot-ack" />acknowledged</span>
          <span class="kpi-num">{{ fmt(totals.by_action['acknowledge'] ?? 0) }}</span>
          <span class="kpi-sub">{{ windowLabel }}</span>
        </div>
        <div class="kpi-cell">
          <span class="kpi-label"><i class="kpi-dot kpi-dot-ttr" />median time-to-resolve</span>
          <span class="kpi-num">{{ fmtMedian(totals.median_ttr_seconds) }}</span>
          <span class="kpi-sub">pooled across the team</span>
        </div>
        <div class="kpi-cell">
          <span class="kpi-label"><i class="kpi-dot kpi-dot-sla" />SLA met</span>
          <span class="kpi-num">{{ teamSla }}</span>
          <span class="kpi-sub">of SLA-bearing handled findings</span>
        </div>
        <div class="kpi-cell">
          <span class="kpi-label"><i class="kpi-dot kpi-dot-crit" />critical cleared</span>
          <span class="kpi-num">{{ fmt(totals.critical_cleared) }}</span>
          <span class="kpi-sub">{{ windowLabel }}</span>
        </div>
      </div>

      <div class="contrib-layout">
        <div class="contrib-main">
          <section class="card-section">
            <div class="card-head">
              <h2>Top contributors</h2>
              <p class="card-sub">most findings resolved · {{ windowLabel }}</p>
            </div>
            <div class="podiums" :class="{ 'podiums-full': podium.length === 3 }">
              <PodiumCard v-for="p in podium" :key="p.row.actor" :row="p.row" :rank="p.rank" />
            </div>
          </section>

          <section class="card-section card-flush">
            <div class="card-head">
              <h2>Leaderboard</h2>
              <p class="card-sub">all contributors · ranked by resolved</p>
            </div>
            <LeaderboardTable :rows="board" :cap="BOARD_CAP" />
          </section>
        </div>

        <section class="card-section contrib-side">
          <div class="card-head">
            <h2>Recent activity</h2>
            <p class="card-sub">from the audit trail</p>
          </div>
          <ActivityFeed :query="query" />
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* band/head scaffolding lives in base.css (shared data-screen grammar) */
.contrib-layout {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 14px;
  align-items: start;
  margin-top: 14px;
}
.contrib-main {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
@media (width <= 1100px) {
  .contrib-layout {
    grid-template-columns: 1fr;
  }
}

/* section cards — the scan-card surface grammar */
.card-section {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 14px 16px;
}
.card-flush {
  padding: 14px 0 0;
}
.card-flush .card-head {
  padding: 0 16px;
}
.card-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 12px;
}
.card-head h2 {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink);
}
.card-sub {
  margin: 0;
  font-size: var(--text-control);
  color: var(--soft);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* prototype .podiums grid — 2·1·3 staging only with a full podium */
.podiums {
  display: grid;
  gap: 12px;
  align-items: end;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  padding-top: 12px;
}
.podiums-full {
  grid-template-columns: 1fr 1.12fr 1fr;
}

/* the ruled KPI band grammar (Overview/finding-detail risk band), static cells */
.kpi-band {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
}
@media (width <= 1100px) {
  .kpi-band {
    grid-template-columns: repeat(3, 1fr);
  }
}
.kpi-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 14px 16px 12px;
}
.kpi-cell + .kpi-cell {
  border-left: 1px solid var(--line2);
}
.kpi-label {
  display: flex;
  align-items: center;
  gap: 7px;
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--soft);
  font-weight: 700;
}
.kpi-num {
  font-family: var(--font-mono);
  font-size: var(--text-stat);
  font-weight: 700;
  color: var(--ink);
  margin-top: 4px;
}
.kpi-sub {
  font-size: var(--text-control);
  color: var(--muted);
}
.kpi-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.kpi-dot-resolved {
  background: var(--state-resolved-solid);
}
.kpi-dot-ack {
  background: var(--state-ack-solid);
}
.kpi-dot-ttr {
  background: var(--teal);
}
.kpi-dot-sla {
  background: var(--coral);
}
.kpi-dot-crit {
  background: var(--sev-critical-solid);
}

.load-error {
  margin: 0;
}
.not-found {
  padding: var(--space-8) 0;
  text-align: center;
  color: var(--soft);
}
.contrib-skel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.skel {
  border-radius: var(--r);
  background: linear-gradient(90deg, var(--line2) 25%, var(--panel) 50%, var(--line2) 75%);
  background-size: 200% 100%;
  animation: contrib-shimmer 1.4s ease-in-out infinite;
}
.skel-band {
  height: 92px;
}
.skel-card {
  height: 320px;
}
@keyframes contrib-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .skel {
    animation: none;
  }
}
</style>
