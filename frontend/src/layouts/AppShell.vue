<script setup lang="ts">
/**
 * Global chrome (SCREENS-v5): 226px slate sidebar (brand lockup, grouped nav, footer health chip
 * + version line) + topbar (cluster switcher · global time picker · search/bell slots (M9f) ·
 * avatar) + the banner stack (degraded · freshness · amber viewing-history). Nav items whose
 * screen is capability-gated are HIDDEN without the capability (A-4).
 */
import { computed, onMounted, onUnmounted } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'

import lockupDark from '@/assets/brand/lockup-dark.svg'
import BackendHealthBanner from '@/components/system/BackendHealthBanner.vue'
import ScannerFreshnessBanner from '@/components/system/ScannerFreshnessBanner.vue'
import GlobalTimePicker from '@/components/time-travel/GlobalTimePicker.vue'
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
  icon: string
  capability?: string
}
const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: 'Posture',
    items: [
      { label: 'Overview', to: '/overview', icon: 'pi-th-large' },
      { label: 'Findings', to: '/findings', icon: 'pi-shield' },
      { label: 'Images', to: '/images', icon: 'pi-box' },
    ],
  },
  {
    group: 'Governance',
    items: [
      { label: 'Audit', to: '/audit', icon: 'pi-list-check' },
      { label: 'Settings', to: '/settings', icon: 'pi-cog', capability: 'can_manage_settings' },
    ],
  },
]

const nav = computed(() =>
  NAV.map((g) => ({
    ...g,
    items: g.items.filter((i) => !i.capability || auth.hasCapability(i.capability)),
  })).filter((g) => g.items.length > 0),
)

const initials = computed(() => (auth.user?.username ?? '?').slice(0, 2).toUpperCase())

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
    <aside class="sidebar">
      <img :src="lockupDark" alt="javv — by Danube Labs" class="lockup" />
      <nav aria-label="Primary">
        <div v-for="g in nav" :key="g.group" class="group">
          <div class="group-label">{{ g.group }}</div>
          <RouterLink v-for="i in g.items" :key="i.to" :to="i.to" class="nav-item">
            <i class="pi" :class="i.icon" aria-hidden="true" />
            {{ i.label }}
          </RouterLink>
        </div>
      </nav>
      <footer class="side-footer">
        <span class="health-chip" :class="{ down: health.degraded }">
          <span class="dot" aria-hidden="true" />
          {{ health.degraded ? 'store degraded' : 'store healthy' }}
        </span>
        <span class="version mono">v{{ APP_VERSION }}</span>
      </footer>
    </aside>

    <div class="main">
      <header class="topbar">
        <select
          v-if="clusterStore.clusters.length"
          class="cluster-switch mono"
          :value="clusterStore.selectedId ?? undefined"
          aria-label="Cluster"
          @change="clusterStore.select(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="c in clusterStore.clusters" :key="c.cluster_id" :value="c.cluster_id">
            {{ c.cluster_name }}
          </option>
        </select>
        <GlobalTimePicker />
        <div class="spacer" />
        <!-- global search + bell land in M9f -->
        <div class="avatar-wrap">
          <span class="avatar" :title="auth.user?.username">{{ initials }}</span>
          <button class="logout" @click="logout">Sign out</button>
        </div>
      </header>

      <BackendHealthBanner />
      <ScannerFreshnessBanner />
      <div v-if="!timeTravel.isNow" class="history-banner" role="status">
        <i class="pi pi-history" aria-hidden="true" />
        Viewing history — as scanned at
        <span class="mono">{{ new Date(timeTravel.t as string).toLocaleString() }}</span>
        <button class="back-to-now" @click="timeTravel.backToNow()">Back to now</button>
      </div>

      <main class="content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-height: 100vh;
}
.sidebar {
  display: flex;
  flex-direction: column;
  width: var(--sidebar-w);
  flex-shrink: 0;
  background: var(--slate);
  color: var(--card);
  padding: 18px 14px;
}
.lockup {
  width: 150px;
  margin: 2px 6px 22px;
}
.group {
  margin-bottom: 18px;
}
.group-label {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--muted);
  padding: 0 8px 6px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 8px;
  border-radius: var(--r-sm);
  color: var(--line2);
  text-decoration: none;
  transition: color 0.12s;
}
.nav-item:hover {
  color: var(--card);
}
.nav-item.router-link-active {
  color: var(--coral);
  background: var(--slate2);
}
.side-footer {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
}
.health-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-sm);
  color: var(--muted);
}
.health-chip .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--health-ok-dot);
}
.health-chip.down .dot {
  background: var(--health-down-fg);
}
.version {
  font-size: var(--text-facet-label);
  color: var(--muted);
}
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 26px;
  background: var(--card);
  border-bottom: 1px solid var(--line);
}
.cluster-switch {
  max-width: 260px;
  padding: 5px 8px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--card);
  color: var(--ink);
  font-size: var(--text-sm);
}
.spacer {
  flex: 1;
}
.avatar-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}
.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--slate2);
  color: var(--card);
  font-size: var(--text-sm);
  font-weight: 600;
}
.logout {
  border: none;
  background: none;
  color: var(--soft);
  font-size: var(--text-sm);
  cursor: pointer;
}
.logout:hover {
  color: var(--coral);
}
.history-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: var(--state-open-bg);
  color: var(--state-open-fg);
  border-bottom: 1px solid var(--state-open-line);
  font-size: var(--text-body);
}
.back-to-now {
  margin-left: auto;
  border: 1px solid var(--state-open-line);
  border-radius: var(--r-chip);
  background: var(--card);
  color: var(--state-open-fg);
  font-size: var(--text-sm);
  padding: 3px 10px;
  cursor: pointer;
}
.content {
  flex: 1;
  max-width: var(--screen-max-w);
  width: 100%;
  margin: 0 auto;
  padding: var(--content-pad);
  padding-bottom: 60px;
}
</style>
