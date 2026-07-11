<script setup lang="ts">
/** KEV tag (prototype `Kev` + `.kev-tag`). Absent KEV renders the muted dash. */
defineProps<{ on: boolean }>()
</script>

<template>
  <span v-if="on" class="kev-tag">KEV</span>
  <span v-else class="muted-dash" aria-label="not in KEV">-</span>
</template>

<style scoped>
/* the one true alarm chip earns real depth (language A): gradient fill + inner highlight */
.kev-tag {
  font-family: var(--font-mono);
  font-size: var(--text-chip-sm);
  font-weight: 700;
  letter-spacing: 0.05em;
  color: var(--kev-fg);
  background: var(--kev-grad);
  padding: 2.5px 7px;
  border-radius: 5px;
  box-shadow: inset 0 1px 0 var(--chip-hi), 0 1px 2px var(--kev-drop);
}
.muted-dash {
  color: var(--dash-muted);
}
</style>
