<script setup lang="ts">
/** Scanner tag (prototype `.scanner-tag`/`.sc-*`). Per-scanner identity is sacred — one tag per row. */
defineProps<{ name: string }>()
</script>

<template>
  <span class="scanner-tag" :data-scanner="name.toLowerCase()">{{ name }}</span>
</template>

<style scoped>
/* language A: derived tint + inset ring from the scanner hue — identity, not status,
   so no dot and no escalation (it never competes with the severity chip) */
.scanner-tag {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 5px;
  letter-spacing: 0.02em;
}
.scanner-tag[data-scanner='trivy'] {
  background: var(--scanner-trivy-bg);
  color: var(--scanner-trivy-fg);
  box-shadow: inset 0 0 0 1px var(--scanner-trivy-line);
}
.scanner-tag[data-scanner='grype'] {
  background: var(--scanner-grype-bg);
  color: var(--scanner-grype-fg);
  box-shadow: inset 0 0 0 1px var(--scanner-grype-line);
}
</style>
