<script setup lang="ts">
/** Reading text for one guide section: a readable measure and paragraph rhythm, so every
 * layout that hosts a section sets its words the same way. */
</script>

<template>
  <div class="guide-prose"><slot /></div>
</template>

<style scoped>
.guide-prose {
  max-width: 72ch;
  color: var(--ink);
  font-size: var(--text-body);
  line-height: 1.6;
}
.guide-prose :slotted(p) {
  margin: 0 0 var(--space-3);
}
.guide-prose :slotted(ul) {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0 0 var(--space-3);
  padding-left: 18px;
}
.guide-prose :slotted(:last-child) {
  margin-bottom: 0;
}
.guide-prose :slotted(strong) {
  font-weight: 600;
}
.guide-prose :slotted(.ui-name) {
  font-weight: 600;
  white-space: nowrap;
}
</style>
