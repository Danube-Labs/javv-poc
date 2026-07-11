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
    <i v-if="dot" class="sev-dot" aria-hidden="true" />{{ level.toUpperCase() }}
  </span>
</template>

<style scoped>
/* Chip language A (operator ruling 2026-07-11): one derived hue per level (tint + inset
   ring from the -solid), visual weight ESCALATES — critical renders solid with an inner
   highlight, high carries the heavier ring, the tail levels sit near-neutral. */
.sev {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-chip);
  font-weight: 600;
  letter-spacing: 0.05em;
  padding: 3px 9px 3px 8px;
  border-radius: var(--r-chip);
  font-family: var(--font-mono);
}
.sev-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
}

/* critical = the solid alarm (escalation top) — dot inverts; AA-proven white text (5.9:1) */
.sev[data-sev='critical'] {
  background: var(--sev-critical-solid);
  color: var(--kev-fg);
  box-shadow: inset 0 1px 0 var(--chip-hi), 0 1px 2px var(--chip-crit-drop);
}
.sev[data-sev='critical'] .sev-dot { background: var(--kev-fg); }
.sev[data-sev='high'] { background: var(--sev-high-bg); color: var(--sev-high-fg); box-shadow: inset 0 0 0 1.5px var(--sev-high-ring); }
.sev[data-sev='high'] .sev-dot { background: var(--sev-high-solid); }
.sev[data-sev='medium'] { background: var(--sev-medium-bg); color: var(--sev-medium-fg); box-shadow: inset 0 0 0 1px var(--sev-medium-line); }
.sev[data-sev='medium'] .sev-dot { background: var(--sev-medium-solid); }
.sev[data-sev='low'] { background: var(--sev-low-bg); color: var(--sev-low-fg); box-shadow: inset 0 0 0 1px var(--sev-low-line); }
.sev[data-sev='low'] .sev-dot { background: var(--sev-low-solid); }
.sev[data-sev='negligible'] { background: var(--sev-negligible-bg); color: var(--sev-negligible-fg); box-shadow: inset 0 0 0 1px var(--sev-negligible-line); }
.sev[data-sev='negligible'] .sev-dot { background: var(--sev-negligible-solid); }
.sev[data-sev='unknown'] { background: var(--sev-unknown-bg); color: var(--sev-unknown-fg); box-shadow: inset 0 0 0 1px var(--sev-unknown-line); }
.sev[data-sev='unknown'] .sev-dot { background: var(--sev-unknown-solid); }

/* `solid` stays a valid emphasis knob (finding-detail header) — for critical it's already
   the resting look; other levels keep their tinted chip per the AA ruling. */
.sev.sev-solid[data-sev='critical'] { padding: 3px 9px; }
</style>
