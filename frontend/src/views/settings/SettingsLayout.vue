<script setup lang="ts">
/**
 * The settings shell (SCREENS-v5 §13; prototype screens-config.jsx `Settings` → `.set-*` CSS):
 * left sub-nav + scope strip + routed panel. Sections are capability-hidden from the nav (A-4);
 * the router guard reroutes direct hits. Save bars belong to the editable panels, not the shell.
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import AppIcon from '@/components/ui/AppIcon.vue'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'

import { SCOPE_COPY, SETTINGS_SECTIONS } from './sections'

const auth = useAuthStore()
const clusterStore = useClusterStore()
const route = useRoute()

const sections = computed(() => SETTINGS_SECTIONS.filter((s) => auth.hasCapability(s.capability)))
const active = computed(
  () => SETTINGS_SECTIONS.find((s) => route.path.startsWith(`/settings/${s.key}`)) ?? null,
)
const scopeNote = computed(() => {
  if (!active.value) return null
  const copy = SCOPE_COPY[active.value.scope]
  const name = clusterStore.selected?.cluster_name
  return active.value.scope === 'cluster' && name
    ? { ...copy, note: `Applies to ${name} only — other clusters keep their own settings.` }
    : copy
})
</script>

<template>
  <div class="screen">
    <div class="screen-head">
      <div>
        <h1>Settings</h1>
        <p class="screen-sub">
          each section notes whether it applies per cluster, per scanner, or organization-wide
        </p>
      </div>
    </div>

    <div class="set-layout">
      <aside class="set-nav" aria-label="Settings sections">
        <RouterLink
          v-for="s in sections"
          :key="s.key"
          :to="`/settings/${s.key}`"
          class="set-nav-item"
          :class="{ 'set-nav-on': active?.key === s.key }"
        >
          <AppIcon :name="s.icon" :size="15" />
          <span>{{ s.label }}</span>
          <i class="scope-dot" :data-scope="s.scope" :title="SCOPE_COPY[s.scope].label" />
        </RouterLink>
      </aside>

      <div class="set-panel">
        <div v-if="active && scopeNote" class="scope-strip" :data-scope="active.scope">
          <span class="scope-badge">{{ scopeNote.label }}</span>
          <span class="scope-note">{{ scopeNote.note }}</span>
        </div>
        <RouterView />
      </div>
    </div>
  </div>
</template>

<style scoped>
/* prototype .set-layout / .set-nav / .scope-* ported onto tokens */
.set-layout {
  display: grid;
  grid-template-columns: 198px 1fr;
  gap: 18px;
  align-items: stretch;
}
.set-nav {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-self: start;
}
.set-nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 0;
  background: transparent;
  color: var(--soft);
  padding: 9px 11px;
  border-radius: 9px;
  font-size: var(--text-body);
  text-align: left;
  text-decoration: none;
  transition:
    background var(--dur-quick) var(--ease-out),
    color var(--dur-quick) var(--ease-out);
}
.set-nav-item:hover {
  background: var(--card);
  color: var(--ink);
}
.set-nav-item:active {
  background: var(--control-active-bg);
}
.set-nav-item:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.set-nav-on {
  background: var(--card);
  color: var(--ink);
  font-weight: 600;
  box-shadow: var(--shadow);
}
.set-nav-on svg {
  color: var(--coral);
}
.scope-dot {
  position: absolute;
  right: 9px;
  top: 50%;
  transform: translateY(-50%);
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
[data-scope='cluster'] {
  --sc: var(--scope-cluster);
}
[data-scope='scanner'] {
  --sc: var(--scope-scanner);
}
[data-scope='org'] {
  --sc: var(--scope-org);
}
.scope-dot {
  background: var(--sc);
}
.scope-strip {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 9px 13px;
  border-radius: 10px;
  margin-bottom: 14px;
  border: 1px solid var(--line2);
  background: var(--panel);
  border-left: 3px solid var(--sc);
}
.scope-badge {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--kev-fg);
  background: var(--sc);
  padding: 3px 9px;
  border-radius: 6px;
  flex: none;
}
.scope-note {
  font-size: var(--text-sweep-strong);
  color: var(--soft);
}
.set-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
@media (width <= 1100px) {
  .set-layout {
    grid-template-columns: 1fr;
  }
  .set-nav {
    flex-direction: row;
    flex-wrap: wrap;
    position: static;
  }
}
</style>
