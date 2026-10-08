<script setup lang="ts">
import AppIcon from '@/components/ui/AppIcon.vue'
import { useHealthStore } from '@/stores/health'

const health = useHealthStore()
</script>

<template>
  <Transition name="t-fade">
    <div v-if="health.bannerVisible" class="sys-line tone-down" role="alert">
      <AppIcon name="alert" :size="15" />
      <span v-if="health.reason === 'backend'">The backend is not answering. Screens cannot load until it is back.</span>
      <span v-else>Search backend unavailable. Check OpenSearch health.</span>
      <button class="dismiss" aria-label="Dismiss" @click="health.dismiss()">
        ×
      </button>
    </div>
  </Transition>
</template>

<style scoped>
.dismiss {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  cursor: default;
  padding: 4px;
}
</style>
