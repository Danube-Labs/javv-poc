<script setup lang="ts">
/**
 * About & guide (issue 341): what this install runs, and how to read JAVV. Reachable from the
 * Help nav group and from the sidebar footer's version lines, by every signed-in user, and live
 * even before any cluster enrolls (`isColdStart` exempts the `help` section). Each card is
 * self-contained; this view only lays them out and passes the selected cluster.
 */
import AboutLinksCard from '@/components/about/AboutLinksCard.vue'
import RunningStackCard from '@/components/about/RunningStackCard.vue'
import { useClusterStore } from '@/stores/cluster'

const clusterStore = useClusterStore()
</script>

<template>
  <div class="screen">
    <div class="screen-head">
      <div class="head-card head-card-fluid">
        <h1>About &amp; guide</h1>
        <p class="head-note">what this install runs, and how to read JAVV</p>
      </div>
    </div>
    <div class="about-grid">
      <RunningStackCard
        :cluster-id="clusterStore.selectedId"
        :cluster-name="clusterStore.selected?.cluster_name ?? null"
      />
      <AboutLinksCard />
    </div>
  </div>
</template>

<style scoped>
.about-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: var(--grid-gap);
  align-items: start;
}
@media (max-width: 1120px) {
  .about-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
