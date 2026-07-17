<script setup lang="ts">
/**
 * THE slideover skeleton (ModalShell's right-drawer sibling; ui.nuxt.com USlideover grammar
 * on JAVV tokens): scrim + right-anchored panel + head/body slots, carrying the ruled dismiss
 * contract (DESIGN.md §2) — Escape, outside-click, visible ✕. For tall workflows that want
 * the page context to stay visible behind them (triage, future notification rail).
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
  <Transition name="t-slideover" appear>
    <div class="so-scrim" @click.self="emit('close')">
      <div
        class="so-panel"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        :style="{ width: `min(${width ?? 440}px, 100%)` }"
      >
        <div class="so-head">
          <div>
            <h3>{{ title }}</h3>
            <p v-if="subtitle" class="so-sub">{{ subtitle }}</p>
          </div>
          <button type="button" class="so-close" aria-label="Close" @click="emit('close')">✕</button>
        </div>
        <div class="so-body"><slot /></div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.so-scrim {
  position: fixed;
  inset: 0;
  background: var(--scrim);
  z-index: 80;
  display: flex;
  justify-content: flex-end;
}
.so-panel {
  background: var(--card);
  border-left: 1px solid var(--line);
  box-shadow: var(--shadow);
  height: 100%;
  display: flex;
  flex-direction: column;
}
/* the B2 slate band — same register as the table heads + triage head */
.so-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  background: var(--table-head-bg);
  color: var(--table-head-fg);
  flex: none;
}
.so-head h3 {
  margin: 0;
}
.so-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  opacity: 0.75;
}
.so-close {
  border: 0;
  background: transparent;
  color: var(--table-head-fg);
  font-size: var(--text-body);
  cursor: default;
  padding: 2px 6px;
  border-radius: var(--r-sm);
}
.so-close:hover {
  background: var(--table-head-line);
}
.so-body {
  overflow-y: auto;
  flex: 1;
}

/* drawer motion: slide from the right; scrim fades (transform/opacity only) */
.t-slideover-enter-active,
.t-slideover-leave-active {
  transition: opacity 0.16s ease-out;
}
.t-slideover-enter-active .so-panel,
.t-slideover-leave-active .so-panel {
  transition: transform 0.18s ease-out;
}
.t-slideover-enter-from,
.t-slideover-leave-to {
  opacity: 0;
}
.t-slideover-enter-from .so-panel,
.t-slideover-leave-to .so-panel {
  transform: translateX(24px);
}
@media (prefers-reduced-motion: reduce) {
  .t-slideover-enter-active,
  .t-slideover-leave-active,
  .t-slideover-enter-active .so-panel,
  .t-slideover-leave-active .so-panel {
    transition: none;
  }
}
</style>
