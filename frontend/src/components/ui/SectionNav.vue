<script setup lang="ts">
/**
 * A screen's left section menu (prototype screens-config.jsx `.set-nav`, ported onto tokens):
 * a sticky card of icon + label rows, the active row in the coral wash. Settings uses it for
 * its sub-pages and the Guide for its in-page sections; `to` is whatever RouterLink takes, a
 * path or a `{ hash }`. The `trail` slot carries a row's extra mark (Settings' scope dot).
 */
import type { RouteLocationRaw } from 'vue-router'

import AppIcon from '@/components/ui/AppIcon.vue'
import type { IconName } from '@/components/ui/AppIcon.vue'

export interface SectionNavItem {
  key: string
  label: string
  icon: IconName
  to: RouteLocationRaw
}

withDefaults(
  defineProps<{
    items: readonly SectionNavItem[]
    active: string | null
    label: string
    /** `page` for rows that open another screen, `location` for rows within this one. */
    current?: 'page' | 'location'
  }>(),
  { current: 'page' },
)
</script>

<template>
  <nav class="snav" :aria-label="label">
    <RouterLink
      v-for="item in items"
      :key="item.key"
      :to="item.to"
      class="snav-item"
      :class="{ 'snav-on': active === item.key }"
      :aria-current="active === item.key ? current : undefined"
    >
      <AppIcon :name="item.icon" :size="15" />
      <span>{{ item.label }}</span>
      <slot name="trail" :item="item" />
    </RouterLink>
  </nav>
</template>

<style scoped>
/* the nav rides in a card track (Nuxt UI pill-tabs grammar, inverted for our darker canvas:
   the container is the card, selection takes the coral wash, the time-preset idiom) */
.snav {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-self: start;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 6px;
}
.snav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  /* the 1px border is reserved at rest so the hover border doesn't shift the row */
  border: 1px solid transparent;
  background: transparent;
  color: var(--soft);
  padding: 8px 10px;
  border-radius: 9px;
  font-size: var(--text-body);
  text-align: left;
  text-decoration: none;
  transition:
    background var(--dur-quick) var(--ease-out),
    border-color var(--dur-quick) var(--ease-out),
    color var(--dur-quick) var(--ease-out);
}
.snav-item:hover {
  background: var(--panel);
  border-color: var(--control-hover-line);
  color: var(--ink);
}
.snav-item:active {
  background: var(--control-active-bg);
}
.snav-item:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.snav-on,
.snav-on:hover {
  background: var(--dd-on-bg);
  border-color: transparent;
  color: var(--coral-text);
  font-weight: 600;
}
.snav-on svg {
  color: var(--coral);
}
@media (width <= 1100px) {
  .snav {
    flex-direction: row;
    flex-wrap: wrap;
    position: static;
  }
}
@media (prefers-reduced-motion: reduce) {
  .snav-item {
    transition: none;
  }
}
</style>
