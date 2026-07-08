<script setup lang="ts">
defineProps<{ title: string; bolt: string }>()
</script>

<template>
  <section>
    <h1>{{ title }}</h1>
    <p class="hint">This screen lands with <span class="mono">{{ bolt }}</span>.</p>
  </section>
</template>

<style scoped>
.hint {
  color: var(--soft);
}
</style>
