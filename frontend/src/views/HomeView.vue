<script setup lang="ts">
import { SEVERITIES } from '@/styles/tokens'
</script>

<template>
  <main class="home">
    <h1>javv</h1>
    <p class="subtitle">just another vulnerability viewer — shell lands in M9a slice 3.</p>
    <div class="sev-row">
      <span v-for="s in SEVERITIES" :key="s" class="sev-chip" :data-sev="s">{{ s }}</span>
    </div>
  </main>
</template>

<style scoped>
.home {
  max-width: var(--screen-max-w);
  margin: 0 auto;
  padding: var(--content-pad);
}
.subtitle {
  color: var(--soft);
}
.sev-row {
  display: flex;
  gap: 8px;
  margin-top: var(--grid-gap);
}
.sev-chip {
  padding: 2px 8px;
  border-radius: var(--r-chip);
  border: 1px solid;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  text-transform: uppercase;
}
.sev-chip[data-sev='critical'] { color: var(--sev-critical-fg); background: var(--sev-critical-bg); border-color: var(--sev-critical-line); }
.sev-chip[data-sev='high'] { color: var(--sev-high-fg); background: var(--sev-high-bg); border-color: var(--sev-high-line); }
.sev-chip[data-sev='medium'] { color: var(--sev-medium-fg); background: var(--sev-medium-bg); border-color: var(--sev-medium-line); }
.sev-chip[data-sev='low'] { color: var(--sev-low-fg); background: var(--sev-low-bg); border-color: var(--sev-low-line); }
.sev-chip[data-sev='negligible'] { color: var(--sev-negligible-fg); background: var(--sev-negligible-bg); border-color: var(--sev-negligible-line); }
.sev-chip[data-sev='unknown'] { color: var(--sev-unknown-fg); background: var(--sev-unknown-bg); border-color: var(--sev-unknown-line); }
</style>
