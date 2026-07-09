<script setup lang="ts">
/**
 * Column visibility + density menu (prototype filters.jsx `ColumnsMenu` + `.cols-menu`/`.seg`
 * CSS). Generic over a `cols` list so future grid screens (images, audit) reuse it — the
 * parent owns the hidden-set and density state (and any persistence).
 */
import { onMounted, onUnmounted, ref, useTemplateRef } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'

defineProps<{
  cols: readonly (readonly [string, string])[]
  hidden: ReadonlySet<string>
  dense: boolean
}>()

const emit = defineEmits<{ toggleCol: [key: string]; 'update:dense': [dense: boolean] }>()

const open = ref(false)
const wrap = useTemplateRef<HTMLElement>('wrap')

function onDocMousedown(e: MouseEvent) {
  if (wrap.value && !wrap.value.contains(e.target as Node)) open.value = false
}
onMounted(() => document.addEventListener('mousedown', onDocMousedown))
onUnmounted(() => document.removeEventListener('mousedown', onDocMousedown))
</script>

<template>
  <div ref="wrap" class="dropdown cols-dd" @keydown.esc="open = false">
    <button class="btn-mini" @click="open = !open"><AppIcon name="columns" :size="13" />Columns</button>
    <div v-if="open" class="dd-menu cols-menu">
      <div class="dd-head">Density</div>
      <div class="seg">
        <button class="seg-opt" :class="{ 'seg-on': dense }" @click="emit('update:dense', true)">
          Compact
        </button>
        <button class="seg-opt" :class="{ 'seg-on': !dense }" @click="emit('update:dense', false)">
          Comfortable
        </button>
      </div>
      <div class="dd-head">Columns</div>
      <button
        v-for="[key, label] in cols"
        :key="key"
        class="facet-row"
        :class="{ 'facet-on': !hidden.has(key) }"
        @click="emit('toggleCol', key)"
      >
        <span class="facet-check" />
        <span class="facet-label">{{ label }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.dropdown {
  position: relative;
}
.cols-dd {
  flex: none;
}
.btn-mini {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: var(--text-quiet-action);
  padding: 5px 9px;
  background: var(--panel);
  border: 1px solid var(--line);
  color: var(--soft);
  border-radius: 7px;
  cursor: pointer;
}
.btn-mini:hover {
  border-color: var(--control-hover-line);
  color: var(--ink);
}
.btn-mini:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.dd-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  left: auto;
  z-index: 30;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  box-shadow: var(--dd-shadow);
  padding: 6px;
  min-width: 230px;
}
.dd-head {
  font-family: var(--font-mono);
  font-size: var(--text-dd-head);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--soft);
  padding: 8px 12px 6px;
}
.seg {
  display: inline-flex;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 9px;
  padding: 3px;
  gap: 2px;
  margin: 2px 8px 8px;
}
.seg-opt {
  border: 0;
  background: transparent;
  color: var(--soft);
  font-size: var(--text-control);
  padding: 5px 12px;
  border-radius: 6px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
}
.seg-opt:hover {
  color: var(--ink);
}
.seg-opt:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.seg-on {
  background: var(--card);
  color: var(--ink);
  box-shadow: var(--shadow);
}
.facet-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 5px 8px;
  border-radius: 7px;
  text-align: left;
  color: var(--soft);
  font-size: var(--text-control);
  cursor: pointer;
}
.facet-row:hover {
  background: var(--panel);
}
.facet-row:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.facet-check {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  border: 1.5px solid var(--facet-check-line);
  flex: none;
  transition: 0.1s;
}
.facet-on .facet-check {
  background: var(--coral);
  border-color: var(--coral);
  box-shadow: inset 0 0 0 2px var(--card);
}
.facet-on {
  color: var(--ink);
  font-weight: 500;
}
.facet-label {
  flex: 1;
}
</style>
