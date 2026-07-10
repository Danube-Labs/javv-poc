<script setup lang="ts">
/**
 * THE dropdown behavior shell (DESIGN.md §2 dismiss contract): owns open state,
 * outside-mousedown and document-level Escape, and the relative anchor. Consumers own the
 * trigger (slot `trigger`, given `open`/`toggle`/`close`) and the menu markup (default slot,
 * given `close`) — positioning and styling stay theirs.
 */
import { onMounted, onUnmounted, useTemplateRef } from 'vue'

const open = defineModel<boolean>('open', { default: false })
const wrap = useTemplateRef<HTMLElement>('wrap')

function toggle() {
  open.value = !open.value
}
function close() {
  open.value = false
}
function onDocMousedown(e: MouseEvent) {
  if (open.value && wrap.value && !wrap.value.contains(e.target as Node)) close()
}
function onDocKeydown(e: KeyboardEvent) {
  if (open.value && e.key === 'Escape') close()
}
onMounted(() => {
  document.addEventListener('mousedown', onDocMousedown)
  document.addEventListener('keydown', onDocKeydown)
})
onUnmounted(() => {
  document.removeEventListener('mousedown', onDocMousedown)
  document.removeEventListener('keydown', onDocKeydown)
})
</script>

<template>
  <div ref="wrap" class="ui-dd">
    <slot name="trigger" :open="open" :toggle="toggle" :close="close" />
    <slot v-if="open" :close="close" />
  </div>
</template>

<style scoped>
.ui-dd {
  position: relative;
}
</style>
