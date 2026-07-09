<script setup lang="ts">
/** The prototype's cluster switcher: glyph + name + mono cluster_id, dropdown per cluster_id. */
import { computed, onMounted, onUnmounted, ref } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import { useClusterStore } from '@/stores/cluster'

const clusterStore = useClusterStore()
const open = ref(false)
const wrap = ref<HTMLElement | null>(null)

const selected = computed(() => clusterStore.selected)
const glyph = (name: string) => (name[0] ?? '?').toUpperCase()

function onDocClick(e: MouseEvent) {
  if (wrap.value && !wrap.value.contains(e.target as Node)) open.value = false
}
onMounted(() => document.addEventListener('mousedown', onDocClick))
onUnmounted(() => document.removeEventListener('mousedown', onDocClick))
</script>

<template>
  <div v-if="selected" ref="wrap" class="cluster-dd" @keydown.esc="open = false">
    <button class="cluster-btn" @click="open = !open">
      <span class="glyph">{{ glyph(selected.cluster_name) }}</span>
      <span class="info">
        <span class="name">{{ selected.cluster_name }}</span>
        <span class="id mono">{{ selected.cluster_id }}</span>
      </span>
      <AppIcon name="chevron" :size="14" class="chev" :class="{ open }" />
    </button>
    <div v-if="open" class="menu">
      <div class="head">Clusters · by cluster_id</div>
      <button
        v-for="c in clusterStore.clusters"
        :key="c.cluster_id"
        class="item"
        :class="{ on: c.cluster_id === clusterStore.selectedId }"
        @click="clusterStore.select(c.cluster_id); open = false"
      >
        <span class="glyph sm">{{ glyph(c.cluster_name) }}</span>
        <span class="info">
          <span class="name">{{ c.cluster_name }}</span>
          <span class="id mono">{{ c.cluster_id }}</span>
        </span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.cluster-dd {
  position: relative;
}
.cluster-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 10px;
  padding: 6px 10px;
  color: var(--ink);
  cursor: pointer;
  max-width: 320px;
}
.glyph {
  width: 26px;
  height: 26px;
  border-radius: 7px;
  background: var(--slate);
  color: var(--side-brand-fg);
  display: grid;
  place-items: center;
  font-weight: 600;
  font-size: var(--text-body);
  flex: none;
}
.glyph.sm {
  width: 24px;
  height: 24px;
  font-size: var(--text-mono-cell);
}
.info {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
  text-align: left;
  min-width: 0;
}
.name {
  font-size: var(--text-body);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.id {
  font-size: var(--text-facet-label);
  color: var(--soft);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chev {
  color: var(--soft);
  transition: transform 0.12s;
}
.chev.open {
  transform: rotate(90deg);
}
.menu {
  position: absolute;
  top: 110%;
  left: 0;
  z-index: 30;
  min-width: 300px;
  padding: 6px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  box-shadow: var(--shadow);
}
.head {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--soft);
  padding: 6px 8px;
}
.item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 6px 8px;
  border: none;
  border-radius: var(--r-chip);
  background: none;
  color: var(--ink);
  cursor: pointer;
  text-align: left;
}
.item:hover {
  background: var(--row-hover);
}
.item.on {
  background: var(--panel);
}
</style>
