<script setup lang="ts">
/**
 * The page for an address that matches no route (issue 674). No prototype screen: the grammar
 * is ui.nuxt.com's Error (the shell stays; centred status code, title, message, one primary
 * way out), ruled on built A/B specimens 2026-10-02. It lives inside the shell, so the sidebar
 * and the auth gate still apply: a signed-out visitor to a bad address lands on login.
 */
import { useRoute, useRouter } from 'vue-router'

import ErrorPage from '@/components/system/ErrorPage.vue'
import UiButton from '@/components/ui/UiButton.vue'

const route = useRoute()
const router = useRouter()
// vue-router records the in-app page we came from; a bad address opened cold has none, and a
// "Go back" that does nothing is worse than no button
const cameFromApp = typeof window.history.state?.back === 'string'
</script>

<template>
  <ErrorPage
    code="404"
    title="Page not found"
    hint="There is no page at this address. It may have moved, or the link may be mistyped."
    :detail="route.path"
  >
    <UiButton variant="primary" @click="router.push({ name: 'overview' })">Back to Overview</UiButton>
    <UiButton v-if="cameFromApp" variant="control" @click="router.back()">Go back</UiButton>
  </ErrorPage>
</template>
