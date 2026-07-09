<script setup lang="ts">
/**
 * Cursor-mode pager (prototype `Pager` + `.pager` CSS, adapted): the shipped M6 contract pages
 * by PIT cursor — prev/next over the visited stack, NO numbered jumps (bolt README 2026-07-09).
 * Total is the server's; the "showing X–Y" range is display arithmetic on server numbers only.
 */
import { computed } from 'vue'

const props = defineProps<{
  total: number
  page: number
  size: number
  shown: number
  hasPrev: boolean
  hasNext: boolean
}>()

const emit = defineEmits<{ prev: []; next: []; 'update:size': [size: number] }>()

const SIZES = [10, 25, 50]
const range = computed(() => {
  if (props.total === 0 || props.shown === 0) return null
  const start = props.page * props.size + 1
  return { start, end: start + props.shown - 1 }
})
const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <div class="pager">
    <span class="pager-info">
      {{ range ? `Showing ${fmt(range.start)}–${fmt(range.end)} of ${fmt(total)}` : 'No results' }}
    </span>
    <div class="pager-right">
      <label class="pager-size">
        Rows per page
        <select :value="size" @change="emit('update:size', Number(($event.target as HTMLSelectElement).value))">
          <option v-for="s in SIZES" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <div class="pager-btns">
        <button :disabled="!hasPrev" @click="emit('prev')">Prev</button>
        <button :disabled="!hasNext" @click="emit('next')">Next</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
}
.pager-info {
  font-size: var(--text-quiet-action);
  color: var(--soft);
  font-family: var(--font-mono);
}
.pager-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.pager-size {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: var(--text-sm);
  color: var(--soft);
  font-family: var(--font-mono);
}
.pager-size select {
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: 7px;
  padding: 4px 6px;
  font-size: var(--text-quiet-action);
  color: var(--ink);
  font-family: inherit;
  outline: none;
}
.pager-size select:focus {
  border-color: var(--coral);
}
.pager-btns {
  display: flex;
  gap: 5px;
}
.pager-btns button {
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: 7px;
  padding: 5px 10px;
  font-size: var(--text-control);
  color: var(--soft);
  min-width: 32px;
  cursor: pointer;
}
.pager-btns button:disabled {
  opacity: 0.45;
  cursor: default;
}
.pager-btns button:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
</style>
