<script setup lang="ts">
/**
 * The page for an address that matches no route (issue 674). No prototype screen: the grammar
 * is ui.nuxt.com's Error (the shell stays; centred status code, title, message, one primary
 * way out), ruled on built A/B specimens 2026-10-02. It lives inside the shell, so the sidebar
 * and the auth gate still apply: a signed-out visitor to a bad address lands on login.
 */
import { useRoute, useRouter } from 'vue-router'

import UiButton from '@/components/ui/UiButton.vue'

const route = useRoute()
const router = useRouter()
// vue-router records the in-app page we came from; a bad address opened cold has none, and a
// "Go back" that does nothing is worse than no button
const cameFromApp = typeof window.history.state?.back === 'string'
</script>

<template>
  <section class="screen not-found">
    <div class="nf-body">
      <p class="nf-code" aria-hidden="true">404</p>
      <h1>Page not found</h1>
      <p class="nf-hint">There is no page at this address. It may have moved, or the link may be mistyped.</p>
      <p class="nf-path mono-cell">{{ route.path }}</p>
      <div class="nf-actions">
        <UiButton variant="primary" @click="router.push({ name: 'overview' })">Back to Overview</UiButton>
        <UiButton v-if="cameFromApp" variant="control" @click="router.back()">Go back</UiButton>
      </div>
    </div>
  </section>
</template>

<style scoped>
.not-found {
  display: grid;
  place-items: center;
  min-height: 62vh;
}
.nf-body {
  text-align: center;
  max-width: 56ch;
}
.nf-code {
  margin: 0 0 6px;
  font-family: var(--font-mono);
  font-size: var(--text-detail-mono);
  font-weight: 700;
  color: var(--coral-text);
}
.nf-body h1 {
  margin: 0 0 8px;
  font-size: var(--text-page-title);
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--ink);
}
.nf-hint {
  margin: 0;
  color: var(--soft);
  font-size: var(--text-body);
}
.nf-path {
  display: inline-block;
  max-width: 100%;
  margin: 12px 0 0;
  padding: 3px 8px;
  border-radius: var(--r-chip);
  background: var(--line2);
  color: var(--soft);
  overflow-wrap: anywhere;
}
.nf-actions {
  margin-top: 18px;
  display: flex;
  justify-content: center;
  gap: 10px;
}
</style>
