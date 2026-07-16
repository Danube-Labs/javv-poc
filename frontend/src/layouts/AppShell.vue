<script setup lang="ts">
/**
 * Global chrome (SCREENS / prototype fidelity): the slate sidebar (extracted to
 * components/chrome/SideNav.vue, issue 384) and the 56px topbar (cluster switcher · global
 * time picker · search/bell slots (M9f, disabled) · avatar), plus the health/freshness/history
 * banners and the routed content column. Owns the global range ⇄ URL sync and the
 * health-polling lifecycle.
 */
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import ClusterSwitcher from '@/components/chrome/ClusterSwitcher.vue'
import SideNav from '@/components/chrome/SideNav.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import BackendHealthBanner from '@/components/system/BackendHealthBanner.vue'
import ScannerFreshnessBanner from '@/components/system/ScannerFreshnessBanner.vue'
import GlobalTimePicker from '@/components/time-travel/GlobalTimePicker.vue'
import ToastStack from '@/components/ui/ToastStack.vue'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useHealthStore } from '@/stores/health'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { lastDataAt } from '@/system/freshness'
import { ttFromQuery, ttToQuery } from '@/system/timeTravelUrl'

const auth = useAuthStore()
const clusterStore = useClusterStore()
const health = useHealthStore()
const timeTravel = useTimeTravelStore()
const router = useRouter()
const route = useRoute()

/* ---- the global range ⇄ URL (restorable-state rule, audit 343) ---- */
// restore BEFORE child views mount, so their first reads already carry the range
const fromUrl = ttFromQuery(route.query)
if (fromUrl) {
  if (fromUrl.t !== null) {
    timeTravel.rewindTo(fromUrl.t)
    timeTravel.setWindow(fromUrl.win, `→ ${lastDataAt(fromUrl.t)}`)
  } else {
    // sub-hour windows label in minutes — rounding 30min to "0 hours" lied (operator catch)
    const hours = fromUrl.win * 24
    const label =
      fromUrl.win >= 1
        ? `Last ${fromUrl.win} day${fromUrl.win === 1 ? '' : 's'}`
        : hours >= 1
          ? `Last ${Math.round(hours)} hour${Math.round(hours) === 1 ? '' : 's'}`
          : `Last ${Math.max(1, Math.round(hours * 60))} minutes`
    timeTravel.setWindow(fromUrl.win, label)
  }
}
// re-stamp on NAVIGATION too — a bare next-page URL would lose the range on ITS refresh
// (operator bug report: set 24h → navigate → refresh → back to 30 days)
watch(
  () => [timeTravel.t, timeTravel.windowDays, route.path] as const,
  ([t, win]) => {
    const tt = ttToQuery(t, win)
    if (route.query.t === (tt.t ?? undefined) && route.query.win === (tt.win ?? undefined)) return
    void router.replace({ query: { ...route.query, t: tt.t, win: tt.win } })
  },
)

const initials = computed(() => (auth.user?.username ?? '?').slice(0, 2).toUpperCase())

/** Section identity echo (§8.5 specimen): the route's sidebar-group accent, exposed as a CSS
 * var the head-card's top bar reads — wayfinding chroma only. */
const sectAccent = computed(() => {
  const sect = route.meta.section as string | undefined
  return sect ? { '--sect-accent': `var(--sect-${sect})` } : {}
})

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
    <SideNav />

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
      <p v-if="clusterStore.failed && clusterStore.clusters.length === 0" class="load-error" role="alert">
        Cluster list unavailable — every read needs it. Check the backend, then reload.
      </p>
      <Transition name="t-fade">
        <div v-if="!timeTravel.isNow" class="history-banner" role="status">
          <AppIcon name="rewind" :size="15" />
          Viewing history — as scanned at
          <span class="mono">{{ new Date(timeTravel.t as string).toLocaleString(undefined, { hour12: false }) }}</span>
          <button class="back-to-now" @click="timeTravel.backToNow()">Back to now</button>
        </div>
      </Transition>

      <main class="content" :class="{ 'content-wide': $route.meta.wide }" :style="sectAccent">
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
