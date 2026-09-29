<script setup lang="ts">
/** The About page's links card (issue 341): where to read on. External, so a new tab. */
import { ABOUT_LINKS } from '@/about/links'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
</script>

<template>
  <SettingsCard title="Read on" subtitle="the operator docs, in the JAVV repository">
    <ul class="about-links">
      <li v-for="link in ABOUT_LINKS" :key="link.href">
        <a class="about-link" :href="link.href" target="_blank" rel="noopener noreferrer">
          <span class="about-link-text">
            <span class="about-link-title">{{ link.title }}</span>
            <span class="about-link-hint">{{ link.hint }}</span>
          </span>
          <AppIcon name="external" :size="13" />
        </a>
      </li>
    </ul>
  </SettingsCard>
</template>

<style scoped>
.about-links {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}
.about-link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 9px 10px;
  margin: 0 -10px;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--ink);
  text-decoration: none;
  transition:
    background var(--dur-quick),
    border-color var(--dur-quick);
}
.about-link:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.about-link:hover .about-link-title {
  color: var(--coral-text);
  text-decoration: underline;
}
.about-link:active {
  background: var(--control-active-bg);
}
.about-link svg {
  flex: none;
  color: var(--soft);
}
.about-link-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.about-link-title {
  font-size: var(--text-body);
  font-weight: 500;
}
.about-link-hint {
  font-size: var(--text-sm);
  color: var(--soft);
}
@media (prefers-reduced-motion: reduce) {
  .about-link {
    transition: none;
  }
}
</style>
