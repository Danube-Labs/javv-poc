<script setup lang="ts">
/**
 * SLA cell (prototype `Sla` + `.sla` CSS). Deadline + overdue are SERVER-computed (B-5) — this
 * component only formats `due_at` as days-remaining for display; it never derives the deadline.
 * The countdown measures from `nowMs` (the D28 display clock: T when rewound) — counting from
 * the wall clock showed "0d" for deadlines that were still open at T.
 */
import { computed } from 'vue'

const props = defineProps<{ dueAt: string | null; overdue: boolean; nowMs?: number }>()

const days = computed(() => {
  if (!props.dueAt) return null
  const ref = props.nowMs ?? Date.now()
  return Math.max(0, Math.ceil((new Date(props.dueAt).getTime() - ref) / 86_400_000))
})
</script>

<template>
  <span v-if="overdue" class="sla sla-over">overdue</span>
  <span v-else-if="days !== null" class="sla" :class="{ 'sla-tight': days <= 2 }" :title="dueAt ?? ''">
    {{ days }}d
  </span>
  <span v-else class="muted-dash">-</span>
</template>

<style scoped>
/* language A: quiet until it isn't — plain mono day counts; overdue is an alarm chip
   with the depth treatment (inner highlight + soft drop), like KEV */
.sla {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--soft);
}
.sla-tight {
  color: var(--sla-tight-fg);
}
.sla-over {
  background: var(--sla-over-bg);
  color: var(--kev-fg);
  font-weight: 700;
  padding: 2.5px 8px;
  border-radius: 5px;
  font-size: var(--text-facet-label);
  box-shadow: inset 0 1px 0 var(--chip-hi), 0 1px 2px var(--chip-crit-drop);
}
.muted-dash {
  color: var(--dash-muted);
}
</style>
