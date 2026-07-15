<script setup lang="ts">
/**
 * The generic dot-and-word status chip (chip language A, QUIET register) — the HealthChip
 * grammar freed from freshness semantics, for statuses that aren't finding states: token
 * active/expired/revoked (M9e), user enabled/disabled, snapshot health. Tone maps onto the
 * health ramp; `muted` is the retired/inert tone (dot only — no halo, nothing to watch).
 */
defineProps<{ tone: 'ok' | 'warn' | 'down' | 'muted'; label: string }>()
</script>

<template>
  <span class="dw" :class="`dw-${tone}`"><i class="dw-dot" aria-hidden="true" />{{ label }}</span>
</template>

<style scoped>
.dw {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
}
.dw-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
}
.dw-ok .dw-dot {
  background: var(--health-ok-dot);
  box-shadow: 0 0 0 3px var(--health-ok-bg);
}
.dw-warn .dw-dot {
  background: var(--health-degraded-dot);
  box-shadow: 0 0 0 3px var(--health-degraded-bg);
}
.dw-down .dw-dot {
  background: var(--health-down-dot);
  box-shadow: 0 0 0 3px var(--health-down-bg);
}
.dw-muted {
  color: var(--soft);
}
.dw-muted .dw-dot {
  background: var(--dash-muted);
}
</style>
