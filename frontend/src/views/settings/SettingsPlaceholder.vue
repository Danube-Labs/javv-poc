<script setup lang="ts">
/** Placeholder panel for §13 sections whose slice hasn't landed yet — swapped out in place. */
import SettingsCard from '@/components/settings/SettingsCard.vue'

defineProps<{ title: string; subtitle: string; slice: string }>()
</script>

<template>
  <SettingsCard :title="title" :subtitle="subtitle">
    <p class="hint">This panel lands with <span class="mono">{{ slice }}</span>.</p>
  </SettingsCard>
</template>

<style scoped>
.hint {
  margin: 14px 0 8px;
  color: var(--soft);
}
</style>
