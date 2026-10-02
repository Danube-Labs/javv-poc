<script setup lang="ts">
/**
 * The one layout for a page that cannot be shown (SCREENS §18): centred on the canvas inside the
 * shell, a short code in mono coral, the title, one plain sentence, an optional detail chip, then
 * the ways out. Grammar: ui.nuxt.com's Error, ruled on built specimens for issue 674.
 */
defineProps<{ code: string; title: string; hint: string; detail?: string }>()
</script>

<template>
  <section class="screen error-page">
    <div class="ep-body">
      <p class="ep-code" aria-hidden="true">{{ code }}</p>
      <h1>{{ title }}</h1>
      <p class="ep-hint">{{ hint }}</p>
      <p v-if="detail" class="ep-detail mono-cell">{{ detail }}</p>
      <div class="ep-actions">
        <slot />
      </div>
    </div>
  </section>
</template>

<style scoped>
.error-page {
  display: grid;
  place-items: center;
  min-height: 62vh;
}
.ep-body {
  text-align: center;
  max-width: 56ch;
}
.ep-code {
  margin: 0 0 6px;
  font-family: var(--font-mono);
  font-size: var(--text-detail-mono);
  font-weight: 700;
  color: var(--coral-text);
}
.ep-body h1 {
  margin: 0 0 8px;
  font-size: var(--text-page-title);
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--ink);
}
.ep-hint {
  margin: 0;
  color: var(--soft);
  font-size: var(--text-body);
}
.ep-detail {
  display: inline-block;
  max-width: 100%;
  margin: 12px 0 0;
  padding: 3px 8px;
  border-radius: var(--r-chip);
  background: var(--line2);
  color: var(--soft);
  overflow-wrap: anywhere;
}
.ep-actions {
  margin-top: 18px;
  display: flex;
  justify-content: center;
  gap: 10px;
}
</style>
