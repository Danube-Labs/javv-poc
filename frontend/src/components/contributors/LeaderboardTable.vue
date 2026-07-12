<script setup lang="ts">
/**
 * The contributors leaderboard (M9d slice 3; prototype table, structure-only onto the shared
 * table template + GridPager). Rows are the server's ≤100-actor board, ordered by resolved
 * (viewModel.sortBoard); pages are display slices of that answer — no client arithmetic beyond
 * slicing and the by_action reads. Severity-mix / pace columns are trimmed (not on the wire).
 * At the board cap the header says so.
 */
import { computed, ref, watch } from 'vue'

import SlaPctChip from '@/components/chips/SlaPctChip.vue'
import ContributorIdentity from '@/components/contributors/ContributorIdentity.vue'
import GridPager from '@/components/findings/GridPager.vue'
import { ackOf, fmtMedian, resolvedOf, sortBoard, type BoardRow } from '@/contributors/viewModel'

const props = defineProps<{
  rows: BoardRow[]
  /** the terms-agg board size — rows.length === cap means "there may be a tail" */
  cap: number
}>()

const ordered = computed(() => sortBoard(props.rows))

const page = ref(0)
const size = ref(10)
watch(
  () => props.rows,
  () => {
    page.value = 0
  },
)
const shown = computed(() =>
  ordered.value.slice(page.value * size.value, (page.value + 1) * size.value),
)
const hasNext = computed(() => (page.value + 1) * size.value < ordered.value.length)
const atCap = computed(() => props.rows.length >= props.cap)

function setSize(next: number) {
  size.value = next
  page.value = 0
}

const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <div class="tbl-wrap">
    <table class="tbl tbl-dense tbl-hover">
      <thead>
        <tr>
          <th class="fit">#</th>
          <th>Person{{ atCap ? ` · top ${cap}` : '' }}</th>
          <th class="r fit">Resolved</th>
          <th class="r fit">Ack.</th>
          <th class="r fit">Actions</th>
          <th class="r fit">Median</th>
          <th class="r fit">SLA</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in shown" :key="row.actor">
          <td class="fit rank-cell mono-cell sm">{{ page * size + i + 1 }}</td>
          <td>
            <ContributorIdentity
              :actor="row.actor"
              :sub="`${fmt(row.handled)} handled`"
              :size="30"
            />
          </td>
          <td class="r fit mono-cell sm strong">{{ fmt(resolvedOf(row)) }}</td>
          <td class="r fit mono-cell sm">{{ fmt(ackOf(row)) }}</td>
          <td class="r fit mono-cell sm">{{ fmt(row.actions) }}</td>
          <td class="r fit mono-cell sm">{{ fmtMedian(row.median_ttr_seconds) }}</td>
          <td class="r fit"><SlaPctChip :pct="row.sla_hit_pct" /></td>
        </tr>
      </tbody>
    </table>
    <div class="board-pager">
      <GridPager
        :total="ordered.length"
        :page="page"
        :size="size"
        :shown="shown.length"
        :has-prev="page > 0"
        :has-next="hasNext"
        @prev="page -= 1"
        @next="page += 1"
        @update:size="setSize"
      />
    </div>
  </div>
</template>

<style scoped>
.rank-cell {
  color: var(--muted);
  font-weight: 700;
}
.strong {
  font-weight: 700;
  color: var(--ink);
}
/* the pager sits inside the table card (card-width surface, not a full-page grid) */
.board-pager {
  padding: 0 12px 10px;
}
.board-pager :deep(.pager) {
  margin-top: 6px;
}
</style>
