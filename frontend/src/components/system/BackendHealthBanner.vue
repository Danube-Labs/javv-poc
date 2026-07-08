<script setup lang="ts">
import { useHealthStore } from '@/stores/health'

const health = useHealthStore()
</script>

<template>
  <div v-if="health.bannerVisible" class="banner" role="alert">
    <i class="pi pi-exclamation-triangle" aria-hidden="true" />
    <span>Search backend unavailable — check OpenSearch health.</span>
    <button class="dismiss" aria-label="Dismiss" @click="health.dismiss()">
      <i class="pi pi-times" aria-hidden="true" />
    </button>
  </div>
</template>

<style scoped>
.banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: var(--health-down-bg);
  color: var(--health-down-fg);
  border-bottom: 1px solid var(--line);
  font-size: var(--text-body);
}
.dismiss {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  padding: 4px;
}
</style>
