<script setup lang="ts">
import { GLOSSARY, glossaryTerm } from '@/about/glossary'
import DisagreementBadge from '@/components/chips/DisagreementBadge.vue'
import EpssBar from '@/components/chips/EpssBar.vue'
import KevTag from '@/components/chips/KevTag.vue'
import StateTag from '@/components/chips/StateTag.vue'
</script>

<template>
  <dl class="glossary">
    <div v-for="entry in GLOSSARY" :key="glossaryTerm(entry)" class="gl-row">
      <dt>
        <span class="gl-term">{{ glossaryTerm(entry) }}</span>
        <KevTag v-if="entry.chip === 'kev'" :on="true" />
        <EpssBar v-else-if="entry.chip === 'epss'" :v="0.42" />
        <DisagreementBadge v-else-if="entry.chip === 'disagree'" />
        <StateTag v-else-if="entry.chip === 'stale' || entry.chip === 'resolved'" :state="entry.chip" />
      </dt>
      <dd>{{ entry.body }}</dd>
    </div>
  </dl>
</template>

<style scoped>
.glossary {
  margin: 0;
}
.gl-row {
  display: grid;
  grid-template-columns: minmax(150px, 220px) minmax(0, 72ch);
  gap: var(--space-4);
  padding: 10px 0;
  border-top: 1px solid var(--line2);
}
.gl-row:first-child {
  border-top: 0;
  padding-top: 0;
}
dt {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  font-weight: 600;
}
dd {
  margin: 0;
  line-height: 1.6;
}
@media (max-width: 1120px) {
  .gl-row {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-1);
  }
}
</style>
