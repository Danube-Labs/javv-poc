<script setup lang="ts">
/**
 * Kit loading skeleton: the shared `.skel` pulse (base.css) wearing the shape of whatever it
 * stands in for. Height is a prop rather than a variant enum — the shapes in use run 22px to
 * 320px and each one mirrors its own placement, so a fixed scale would move pixels.
 *
 * `label` belongs on a skeleton that is its own loading region. Inside a group the wrapper
 * carries `aria-busy`/`aria-label` and the children stay unlabeled, so the region announces once.
 */
withDefaults(defineProps<{ height: number | string; radius?: 'r' | 'sm'; label?: string }>(), {
  radius: 'r',
})
</script>

<template>
  <div
    class="skel"
    :class="{ 'skel--sm': radius === 'sm' }"
    :style="{ height: typeof height === 'number' ? `${height}px` : height }"
    :aria-busy="label ? 'true' : undefined"
    :aria-label="label"
  />
</template>

<style scoped>
.skel--sm {
  border-radius: var(--r-sm);
}
</style>
