<script setup lang="ts">
/** KEV tag (prototype `Kev` + `.kev-tag`). Absent KEV renders the muted dash. */
defineProps<{ on: boolean }>()
</script>

<template>
  <span v-if="on" class="kev-tag">KEV</span>
  <span v-else class="muted-dash" aria-label="not in KEV">-</span>
</template>

<style scoped>
.kev-tag {
  font-family: var(--font-mono);
  font-size: var(--text-chip-sm);
  font-weight: 700;
  letter-spacing: 0.05em;
  color: var(--kev-fg);
  background: var(--kev-bg);
  padding: 2px 6px;
  border-radius: 5px;
}
.muted-dash {
  color: var(--dash-muted);
}
</style>
