<script setup lang="ts">
/** I3 graceful degradation (D38/M16, D39/M11-r2): a screen with no historical read renders
 * this notice INSTEAD of data at T<now, and no code path may attempt one. Defaults carry the
 * all-clusters copy (its original home); M9d's scanner status passes its own (C-1/D39).
 * Prose is --ink on a neutral panel; the info hue lives in the icon only (the "green on
 * green" ruling). */
import AppIcon from '@/components/ui/AppIcon.vue'

withDefaults(defineProps<{ title?: string; body?: string }>(), {
  title: 'Historical all-clusters view is limited until the v1.1 metrics rollup',
  body:
    'Single-cluster screens rewind fully — pick a cluster and travel from its Overview. ' +
    'Fleet-wide numbers at a past T need the metrics rollup (v1.1); until then this screen ' +
    'only answers for now.',
})
</script>

<template>
  <div class="lim-notice" role="status">
    <AppIcon name="info" :size="18" class="lim-icon" />
    <div>
      <h2>{{ title }}</h2>
      <p>{{ body }}</p>
    </div>
  </div>
</template>

<style scoped>
.lim-notice {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 18px 20px;
}
.lim-icon {
  color: var(--teal);
  flex: none;
  margin-top: 1px;
}
.lim-notice h2 {
  margin: 0 0 4px;
  font-size: var(--text-card-title);
  font-weight: 600;
  color: var(--ink);
}
.lim-notice p {
  margin: 0;
  font-size: var(--text-body);
  color: var(--soft);
  max-width: 68ch;
}
</style>
