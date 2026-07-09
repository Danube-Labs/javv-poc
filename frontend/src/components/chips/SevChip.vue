<script setup lang="ts">
/**
 * Severity chip (prototype components.jsx `Sev` + `.sev` CSS). Data colors only — the six D46
 * canonicals via the severity tokens; input is the doc's `severity_canonical` (lowercase),
 * display uppercases (A-1). Unknown input falls back to the `unknown` bucket.
 */
import { computed } from 'vue'

import { SEVERITIES, type Severity } from '@/styles/tokens'

const props = withDefaults(defineProps<{ level: string; solid?: boolean; dot?: boolean }>(), {
  solid: false,
  dot: true,
})

const sev = computed<Severity>(() =>
  (SEVERITIES as readonly string[]).includes(props.level) ? (props.level as Severity) : 'unknown',
)
</script>

<template>
  <span class="sev" :class="{ 'sev-solid': solid }" :data-sev="sev">
    <i v-if="dot && !solid" class="sev-dot" aria-hidden="true" />{{ level.toUpperCase() }}
  </span>
</template>

<style scoped>
.sev {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-chip);
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 3px 8px 3px 7px;
  border-radius: var(--r-chip);
  border: 1px solid transparent;
  font-family: var(--font-mono);
}
.sev-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
/* AA note: white passes only on the critical solid (5.9:1) — use `solid` for critical-grade
   emphasis only; every other level keeps the tinted chip. The [data-sev] selector keeps this
   fg from losing specificity to the per-severity color rules below. */
.sev.sev-solid[data-sev] {
  color: var(--kev-fg);
  border: 0;
  padding: 3px 9px;
}

.sev[data-sev='critical'] { background: var(--sev-critical-bg); color: var(--sev-critical-fg); border-color: var(--sev-critical-line); }
.sev[data-sev='critical'] .sev-dot { background: var(--sev-critical-solid); }
.sev-solid[data-sev='critical'] { background: var(--sev-critical-solid); }
.sev[data-sev='high'] { background: var(--sev-high-bg); color: var(--sev-high-fg); border-color: var(--sev-high-line); }
.sev[data-sev='high'] .sev-dot { background: var(--sev-high-solid); }
.sev-solid[data-sev='high'] { background: var(--sev-high-solid); }
.sev[data-sev='medium'] { background: var(--sev-medium-bg); color: var(--sev-medium-fg); border-color: var(--sev-medium-line); }
.sev[data-sev='medium'] .sev-dot { background: var(--sev-medium-solid); }
.sev-solid[data-sev='medium'] { background: var(--sev-medium-solid); }
.sev[data-sev='low'] { background: var(--sev-low-bg); color: var(--sev-low-fg); border-color: var(--sev-low-line); }
.sev[data-sev='low'] .sev-dot { background: var(--sev-low-solid); }
.sev-solid[data-sev='low'] { background: var(--sev-low-solid); }
.sev[data-sev='negligible'] { background: var(--sev-negligible-bg); color: var(--sev-negligible-fg); border-color: var(--sev-negligible-line); }
.sev[data-sev='negligible'] .sev-dot { background: var(--sev-negligible-solid); }
.sev-solid[data-sev='negligible'] { background: var(--sev-negligible-solid); }
.sev[data-sev='unknown'] { background: var(--sev-unknown-bg); color: var(--sev-unknown-fg); border-color: var(--sev-unknown-line); }
.sev[data-sev='unknown'] .sev-dot { background: var(--sev-unknown-solid); }
.sev-solid[data-sev='unknown'] { background: var(--sev-unknown-solid); }
</style>
