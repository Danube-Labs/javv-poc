<script setup lang="ts">
/**
 * §13.4 — the v4 allowlist table is superseded by decisions (V4-DELTA-2): this section is a
 * pointer to the Decisions queue, where scoped risk-accept / not-affected rules carry
 * justification, expiry and revocation.
 */
import { useRouter } from 'vue-router'

import SettingsCard from '@/components/settings/SettingsCard.vue'
import UiButton from '@/components/ui/UiButton.vue'

const router = useRouter()
</script>

<template>
  <SettingsCard title="Ignore rules" subtitle="superseded by decisions (V4-DELTA-2)">
    <p class="stub-copy">
      Documented, time-boxed exceptions are <b>decisions</b> now — scoped risk-accept and
      not-affected rules with a justification, an expiry and a revocation trail. Review the queue
      on the Decisions screen, or create one from any finding's detail panel; every decision is
      journaled to the audit log.
    </p>
    <UiButton variant="primary" @click="router.push('/approvals')">
      Open the Decisions queue
    </UiButton>
  </SettingsCard>
</template>

<style scoped>
.stub-copy {
  margin: 14px 0;
  max-width: 560px;
  color: var(--ink);
  line-height: 1.5;
}
</style>
