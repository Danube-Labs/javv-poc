<script setup lang="ts">
/**
 * SLA cell (prototype `Sla` + `.sla` CSS). Deadline + overdue are SERVER-computed (B-5) — this
 * component only formats `due_at` as days-remaining for display; it never derives the deadline.
 */
import { computed } from 'vue'

const props = defineProps<{ dueAt: string | null; overdue: boolean }>()

const days = computed(() => {
  if (!props.dueAt) return null
  return Math.max(0, Math.ceil((new Date(props.dueAt).getTime() - Date.now()) / 86_400_000))
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
.sla {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--soft);
}
.sla-tight {
  color: var(--sla-tight-fg);
}
.sla-over {
  background: var(--sla-over-bg);
  color: var(--kev-fg);
  padding: 3px 8px;
  border-radius: 5px;
  font-size: var(--text-facet-label);
}
.muted-dash {
  color: var(--dash-muted);
}
</style>
