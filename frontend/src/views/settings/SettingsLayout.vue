<script setup lang="ts">
/**
 * The settings shell (SCREENS §13; prototype screens-config.jsx `Settings` → `.set-*` CSS):
 * left sub-nav + scope strip + routed panel. Sections are capability-hidden from the nav (A-4);
 * the router guard reroutes direct hits. Save bars belong to the editable panels, not the shell.
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import SectionNav from '@/components/ui/SectionNav.vue'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'

import { SCOPE_COPY, SETTINGS_SECTIONS } from './sections'

const auth = useAuthStore()
const clusterStore = useClusterStore()
const route = useRoute()

const sections = computed(() => SETTINGS_SECTIONS.filter((s) => auth.hasCapability(s.capability)))
const scopeOf = (key: string) => SETTINGS_SECTIONS.find((s) => s.key === key)!.scope
const navItems = computed(() =>
  sections.value.map((s) => ({ key: s.key, label: s.label, icon: s.icon, to: `/settings/${s.key}` })),
)
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
      <div class="head-card head-card-fluid">
        <h1>Settings</h1>
        <p class="head-note">
          each section notes whether it applies per cluster, per scanner, or organization-wide
        </p>
      </div>
    </div>

    <div class="set-layout">
      <SectionNav :items="navItems" :active="active?.key ?? null" label="Settings sections">
        <template #trail="{ item }">
          <i
            class="scope-dot"
            :data-scope="scopeOf(item.key)"
            :title="SCOPE_COPY[scopeOf(item.key)].label"
          />
        </template>
      </SectionNav>

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
/* prototype .set-layout / .scope-* ported onto tokens; the .set-nav menu is SectionNav */
.set-layout {
  display: grid;
  grid-template-columns: var(--section-nav-w) 1fr;
  gap: 18px;
  align-items: stretch;
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
}
</style>
