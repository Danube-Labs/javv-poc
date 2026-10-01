<script setup lang="ts">
/**
 * A "learn more" pointer from a screen into the Guide, landing on one section's anchor.
 *   link     inline words after an explanation already on screen (the freshness banner);
 *   popover  an info icon that opens the section's title and one-line summary, with a link
 *            onward, for a strip with no room for words (the ingest strip).
 * The section is a typed `GuideSectionId`, so a link to a section that doesn't exist fails
 * the type check.
 */
import { computed, ref } from 'vue'

import { GUIDE_SECTIONS, guideHref, type GuideSectionId } from '@/about/guide'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiDropdown from '@/components/ui/UiDropdown.vue'

const props = withDefaults(
  defineProps<{ section: GuideSectionId; variant?: 'link' | 'popover'; label?: string }>(),
  { variant: 'link', label: 'How to read this' },
)

const section = computed(() => GUIDE_SECTIONS.find((s) => s.id === props.section)!)
const open = ref(false)
</script>

<template>
  <RouterLink v-if="variant === 'link'" class="gl-text" :to="guideHref(section.id)">{{
    label
  }}</RouterLink>
  <UiDropdown v-else v-model:open="open" class="gl-pop-wrap">
    <template #trigger="{ toggle }">
      <button
        type="button"
        class="gl-icon"
        :aria-expanded="open"
        :aria-label="`${label}: ${section.title}`"
        @click="toggle"
      >
        <AppIcon name="info" :size="14" />
      </button>
    </template>
    <div class="gl-pop" role="dialog" :aria-label="section.title">
      <p class="gl-pop-title">{{ section.title }}</p>
      <p class="gl-pop-body">{{ section.summary }}</p>
      <RouterLink class="gl-pop-link" :to="guideHref(section.id)" @click="open = false">
        Read more in the guide <AppIcon name="chevron" :size="12" />
      </RouterLink>
    </div>
  </UiDropdown>
</template>

<style scoped>
.gl-text {
  padding: 0 3px;
  border: 1px solid transparent;
  border-radius: var(--r-chip);
  color: inherit;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
  white-space: nowrap;
  transition:
    background var(--dur-quick),
    border-color var(--dur-quick);
}
.gl-text:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.gl-text:active {
  background: var(--control-active-bg);
}
.gl-pop-wrap {
  display: inline-flex;
  vertical-align: middle;
}
.gl-icon {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--r-chip);
  background: transparent;
  color: var(--soft);
  transition:
    background var(--dur-quick),
    border-color var(--dur-quick);
}
.gl-icon:hover,
.gl-icon[aria-expanded='true'] {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
  color: var(--ink);
}
.gl-icon:active {
  background: var(--control-active-bg);
}
.gl-pop {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 30;
  width: 280px;
  padding: 12px 14px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  box-shadow: var(--shadow);
  color: var(--ink);
  font-size: var(--text-body);
  text-align: left;
  white-space: normal;
}
.gl-pop-title {
  margin: 0 0 4px;
  font-weight: 600;
}
.gl-pop-body {
  margin: 0 0 10px;
  color: var(--soft);
  line-height: 1.5;
}
.gl-pop-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: -4px;
  padding: 2px 4px;
  border: 1px solid transparent;
  border-radius: var(--r-chip);
  color: var(--coral-text);
  font-weight: 600;
  text-decoration: none;
  transition:
    background var(--dur-quick),
    border-color var(--dur-quick);
}
.gl-pop-link:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
  text-decoration: underline;
}
.gl-pop-link:active {
  background: var(--control-active-bg);
}
@media (prefers-reduced-motion: reduce) {
  .gl-text,
  .gl-icon,
  .gl-pop-link {
    transition: none;
  }
}
</style>
