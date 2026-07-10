<script setup lang="ts">
/**
 * Global chrome (SCREENS-v5 / prototype fidelity): slate sidebar (226px, collapsible to a 64px
 * icon rail — Nuxt UI sidebar grammar, state persisted per browser) — brand block, grouped
 * nav with the javv stroke icons + coral active bar, sweep-health footer + version line — and
 * the 56px topbar (cluster switcher · global time picker · search/bell slots (M9f, disabled) ·
 * avatar). Nav items whose screen is capability-gated are HIDDEN without the capability (A-4).
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'

import iconSvg from '@/assets/brand/icon.svg'
import ClusterSwitcher from '@/components/chrome/ClusterSwitcher.vue'
import AppIcon, { type IconName } from '@/components/ui/AppIcon.vue'
import BackendHealthBanner from '@/components/system/BackendHealthBanner.vue'
import ScannerFreshnessBanner from '@/components/system/ScannerFreshnessBanner.vue'
import GlobalTimePicker from '@/components/time-travel/GlobalTimePicker.vue'
import ToastStack from '@/components/ui/ToastStack.vue'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useHealthStore } from '@/stores/health'
import { useTimeTravelStore } from '@/stores/timeTravel'

const APP_VERSION = import.meta.env.VITE_APP_VERSION ?? 'dev'

const auth = useAuthStore()
const clusterStore = useClusterStore()
const health = useHealthStore()
const timeTravel = useTimeTravelStore()
const router = useRouter()

interface NavItem {
  label: string
  to: string
  icon: IconName
  capability?: string
}
/* Prototype nav structure (main.jsx Sidebar) — every screen present, owned by its bolt. */
const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: 'Monitor',
    items: [
      { label: 'All clusters', to: '/clusters', icon: 'layers' },
      { label: 'Overview', to: '/overview', icon: 'grid' },
      { label: 'Findings', to: '/findings', icon: 'list' },
      { label: 'Saved views', to: '/views', icon: 'bookmark' },
      { label: 'Scanner status', to: '/scanner-status', icon: 'pulse' },
    ],
  },
  { group: 'Inventory', items: [{ label: 'Running images', to: '/images', icon: 'cube' }] },
  {
    group: 'Audit',
    items: [
      {
        label: 'Approval list',
        to: '/approvals',
        icon: 'shield',
        capability: 'can_accept_audit_final',
      },
      { label: 'Audit log', to: '/audit', icon: 'clock' },
    ],
  },
  { group: 'Insights', items: [{ label: 'Contributors', to: '/contributors', icon: 'award' }] },
  {
    group: 'Configure',
    items: [{ label: 'Settings', to: '/settings', icon: 'gear', capability: 'can_manage_settings' }],
  },
]

const nav = computed(() =>
  NAV.map((g) => ({
    ...g,
    items: g.items.filter((i) => !i.capability || auth.hasCapability(i.capability)),
  })).filter((g) => g.items.length > 0),
)

const initials = computed(() => (auth.user?.username ?? '?').slice(0, 2).toUpperCase())

const SIDEBAR_KEY = 'javv.sidebar.collapsed'
const collapsed = ref(localStorage.getItem(SIDEBAR_KEY) === '1')
function toggleSidebar() {
  collapsed.value = !collapsed.value
  localStorage.setItem(SIDEBAR_KEY, collapsed.value ? '1' : '0')
}

async function logout() {
  await auth.logout()
  await router.push({ name: 'login' })
}

onMounted(() => {
  health.startPolling()
  void clusterStore.fetchClusters()
})
onUnmounted(() => health.stopPolling())
</script>

<template>
  <div class="shell">
    <nav class="sidebar" :class="{ collapsed }" aria-label="Primary">
      <div class="side-top">
        <RouterLink to="/overview" class="side-brand" :title="collapsed ? 'javv — Overview' : undefined">
          <img :src="iconSvg" alt="" width="32" height="32" />
          <span v-if="!collapsed" class="side-word"><b>javv</b><span>by Danube Labs</span></span>
        </RouterLink>
        <button
          class="side-collapse"
          :aria-expanded="!collapsed"
          :title="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
          @click="toggleSidebar"
        >
          <AppIcon name="sidebar" :size="16" />
        </button>
      </div>
      <div class="side-nav">
        <div v-for="g in nav" :key="g.group" class="side-group">
          <div v-if="!collapsed" class="side-group-label">{{ g.group }}</div>
          <div v-else class="side-sep" aria-hidden="true" />
          <RouterLink
            v-for="i in g.items"
            :key="i.to"
            :to="i.to"
            class="side-item"
            :title="collapsed ? i.label : undefined"
          >
            <AppIcon :name="i.icon" :size="17" />
            <span v-if="!collapsed">{{ i.label }}</span>
          </RouterLink>
        </div>
      </div>
      <div class="side-foot">
        <div
          class="sweep"
          :title="collapsed ? `${health.degraded ? 'Store degraded' : 'Store healthy'} · ${clusterStore.clusters.length} cluster(s)` : undefined"
        >
          <span class="sweep-dot" :class="{ down: health.degraded }" aria-hidden="true" />
          <div v-if="!collapsed">
            <b>{{ health.degraded ? 'Store degraded' : 'Store healthy' }}</b>
            <span>{{ clusterStore.clusters.length }} cluster(s) · live</span>
          </div>
        </div>
        <div v-if="!collapsed" class="side-version">v{{ APP_VERSION }} · schema 4 · MVP</div>
      </div>
    </nav>

    <div class="main">
      <header class="topbar">
        <ClusterSwitcher />
        <div class="topbar-mid">
          <GlobalTimePicker />
        </div>
        <div class="topbar-right">
          <div class="global-search" title="Global search lands in M9f">
            <AppIcon name="search" :size="14" />
            <input placeholder="Search CVE, image, package…" disabled aria-label="Global search (M9f)" />
          </div>
          <button class="icon-btn" title="Notifications land in M9f" disabled>
            <AppIcon name="bell" :size="17" />
          </button>
          <span class="avatar" :title="auth.user?.username">{{ initials }}</span>
          <button class="logout" @click="logout">Sign out</button>
        </div>
      </header>

      <BackendHealthBanner />
      <ScannerFreshnessBanner />
      <Transition name="t-fade">
        <div v-if="!timeTravel.isNow" class="history-banner" role="status">
          <AppIcon name="rewind" :size="15" />
          Viewing history — as scanned at
          <span class="mono">{{ new Date(timeTravel.t as string).toLocaleString(undefined, { hour12: false }) }}</span>
          <button class="back-to-now" @click="timeTravel.backToNow()">Back to now</button>
        </div>
      </Transition>

      <main class="content" :class="{ 'content-wide': $route.meta.wide }">
        <RouterView />
      </main>
    </div>

    <ToastStack />
  </div>
</template>

<style scoped>
.shell {
  /* desktop-first ops dashboard: 1024px design floor (audit ruling) — below it the app
     scrolls as ONE intact piece; a true responsive pass is an M9f decision, not an accident */
  min-width: 1024px;
  display: flex;
  min-height: 100vh;
}

/* ---- sidebar (prototype .sidebar family, via the side-chrome tokens) ---- */
.sidebar {
  width: var(--sidebar-w);
  flex: none;
  background: var(--slate);
  color: var(--side-fg);
  display: flex;
  flex-direction: column;
  padding: 16px 14px;
  overflow: hidden;
  transition: width var(--dur-panel) var(--ease-out);
}
.sidebar.collapsed {
  width: var(--sidebar-w-rail);
  padding: 16px 10px;
}
@media (prefers-reduced-motion: reduce) {
  .sidebar {
    transition: none;
  }
}
.side-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding-bottom: 18px;
}
.collapsed .side-top {
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.side-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 6px 8px 0 8px;
  text-decoration: none;
}
.collapsed .side-brand {
  padding: 0;
}
.side-collapse {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  margin-top: 6px;
  border: none;
  border-radius: 7px;
  background: none;
  color: var(--side-label);
  transition:
    background var(--dur-quick),
    color var(--dur-quick);
}
.side-collapse:hover {
  background: var(--side-hover-bg);
  color: var(--side-fg-hover);
}
.side-collapse:active {
  background: var(--side-active-bg);
}
.side-collapse:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.side-word {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}
.side-word b {
  font-size: var(--text-brand-word);
  color: var(--side-brand-fg);
  letter-spacing: -0.03em;
}
.side-word span {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  color: var(--side-credit);
  letter-spacing: 0.04em;
  margin-top: 2px;
}
.side-nav {
  flex: 1;
}
.side-group {
  margin-bottom: 14px;
}
.side-group-label {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--side-label);
  padding: 0 10px 8px;
  white-space: nowrap;
}
.side-sep {
  height: 1px;
  background: var(--side-foot-line);
  margin: 0 8px 10px;
}
.side-item {
  display: flex;
  align-items: center;
  gap: 11px;
  width: 100%;
  padding: 9px 10px;
  border-radius: 9px;
  color: var(--side-fg);
  font-size: var(--text-nav-item);
  text-decoration: none;
  transition: color 0.12s;
  position: relative;
  white-space: nowrap;
}
.collapsed .side-item {
  justify-content: center;
  padding: 9px 0;
}
.side-item:hover {
  background: var(--side-hover-bg);
  color: var(--side-fg-hover);
}
.side-item.router-link-active {
  background: var(--side-on-bg);
  color: var(--side-on-fg);
}
.side-item.router-link-active::before {
  content: '';
  position: absolute;
  left: -14px;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--coral);
}
.collapsed .side-item.router-link-active::before {
  left: -10px;
}
.side-item.router-link-active svg {
  color: var(--amber);
}
.side-foot {
  border-top: 1px solid var(--side-foot-line);
  padding-top: 14px;
  margin-top: 8px;
}
.sweep {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: var(--text-sm);
  color: var(--side-foot-fg);
}
.collapsed .sweep {
  justify-content: center;
  padding: 4px 0;
}
.sweep div {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}
.sweep b {
  color: var(--side-foot-strong);
  font-size: var(--text-sweep-strong);
  font-weight: 500;
}
.sweep span {
  color: var(--side-foot-dim);
  font-size: var(--text-facet-label);
  font-family: var(--font-mono);
}
.sweep-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--health-ok-dot);
  flex: none;
  box-shadow: 0 0 0 3px var(--sweep-ok-ring);
}
.sweep-dot.down {
  background: var(--health-down-fg);
  box-shadow: none;
}
.side-version {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  color: var(--side-version);
  margin-top: 12px;
  padding: 0 2px;
  letter-spacing: 0.04em;
}

/* ---- topbar (prototype .topbar family) ---- */
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.topbar {
  height: 56px;
  flex: none;
  background: var(--card);
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 0 22px;
}
.topbar-mid {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 14px;
}
.global-search {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 10px;
  padding: 6px 10px;
  color: var(--soft);
  width: 230px;
}
.global-search input {
  border: none;
  background: none;
  outline: none;
  width: 100%;
  color: var(--ink);
  font-family: var(--font-ui);
  font-size: var(--text-body);
}
.icon-btn {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--card);
  color: var(--soft);
  cursor: default;
}
.icon-btn:disabled {
  cursor: default;
  opacity: 0.6;
}
.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--slate2);
  color: var(--side-brand-fg);
  font-size: var(--text-sm);
  font-weight: 600;
}
.logout {
  border: none;
  background: none;
  color: var(--soft);
  font-size: var(--text-sm);
  cursor: default;
}
.logout:hover {
  color: var(--coral-text);
}

/* ---- banners + content ---- */
.history-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: var(--state-open-bg);
  /* prose is ink — hue lives in the bg/border/icon, never same-hue words on a tint */
  color: var(--ink);
  border-bottom: 1px solid var(--state-open-line);
  font-size: var(--text-body);
}
.history-banner svg {
  color: var(--state-open-fg);
  flex: none;
}
.back-to-now {
  margin-left: auto;
  border: 1px solid var(--state-open-line);
  border-radius: var(--r-chip);
  background: var(--card);
  color: var(--state-open-fg);
  font-size: var(--text-sm);
  padding: 3px 10px;
  cursor: default;
}
.content {
  flex: 1;
  max-width: var(--screen-max-w);
  width: 100%;
  margin: 0 auto;
  padding: var(--content-pad);
  padding-bottom: 72px;
}
/* data-dense screens (route meta `wide`) use the full viewport instead of the 1380px cap —
   an internal table scrollbar beside dead margin is worse than a wide table (operator ruling). */
.content-wide {
  max-width: none;
}
</style>
