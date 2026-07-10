<script setup lang="ts">
/**
 * THE modal skeleton: scrim + card + head/body/actions slots, carrying the ruled
 * dismiss contract (DESIGN.md §2) once — Escape, outside-click, visible ✕ — so dialogs can't
 * drift apart again. Consumers own only their body content and action buttons.
 */
import { onMounted, onUnmounted } from 'vue'

defineProps<{ title: string; subtitle?: string; width?: number }>()
const emit = defineEmits<{ close: [] }>()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <!-- appear: consumers v-if the whole dialog, so the t-modal entrance plays on mount;
       close stays instant — unmount is what resets consumer form state. -->
  <Transition name="t-modal" appear>
  <div class="modal-scrim" @click.self="emit('close')">
    <div class="modal" role="dialog" aria-modal="true" :aria-label="title" :style="{ width: `min(${width ?? 520}px, 100%)` }">
      <div class="modal-head">
        <div>
          <h3>{{ title }}</h3>
          <p v-if="subtitle" class="modal-sub">{{ subtitle }}</p>
        </div>
        <button type="button" class="modal-close" aria-label="Close" @click="emit('close')">✕</button>
      </div>
      <div class="modal-body"><slot /></div>
      <div class="modal-actions"><slot name="actions" /></div>
    </div>
  </div>
  </Transition>
</template>

<style scoped>
.modal-scrim {
  position: fixed;
  inset: 0;
  background: var(--scrim);
  display: grid;
  place-items: center;
  z-index: 80;
  padding: 24px;
}
.modal {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}
.modal-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 12px;
  border-bottom: 1px solid var(--line2);
}
.modal-head h3 {
  margin: 0;
}
.modal-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.modal-close {
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: var(--r-sm);
  padding: 3px 8px;
  font-size: var(--text-sm);
  color: var(--ink);
  cursor: default;
}
.modal-close:hover {
  border-color: var(--control-hover-line);
}
.modal-body {
  padding: 14px 18px;
  overflow-y: auto;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px 16px;
  border-top: 1px solid var(--line2);
}
</style>
