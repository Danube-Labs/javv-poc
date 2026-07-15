<script setup lang="ts">
/**
 * The settings row grammar (prototype `Row` → `.set-row`): label + hint on the left, control
 * on the right; `stack` flips to label-above for wide controls (chips lists, tables).
 * The label slot takes rich labels (severity chips); the `label` prop is the plain-text case.
 */
defineProps<{ label?: string; hint?: string; stack?: boolean }>()
</script>

<template>
  <div class="set-row" :class="{ 'set-row-stack': stack }">
    <div class="set-row-label">
      <span class="set-row-title"><slot name="label">{{ label }}</slot></span>
      <span v-if="hint" class="set-hint">{{ hint }}</span>
    </div>
    <div class="set-row-ctrl"><slot /></div>
  </div>
</template>

<style scoped>
.set-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 14px 0;
  border-bottom: 1px solid var(--line2);
}
.set-row:last-child {
  border-bottom: 0;
  padding-bottom: 2px;
}
.set-row-stack {
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
}
.set-row-label {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-width: 340px;
}
.set-row-title {
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--ink);
}
.set-hint {
  font-size: var(--text-sweep-strong);
  color: var(--soft);
  line-height: 1.45;
}
.set-row-ctrl {
  flex: none;
}
.set-row-stack .set-row-ctrl {
  flex: 1;
}
</style>
