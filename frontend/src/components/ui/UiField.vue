<script setup lang="ts">
/**
 * THE labeled-field group: the mono uppercase micro-label (+ optional parenthesized hint)
 * above any control. Owns the 14px band / 6px label-to-control rhythm; `first` zeroes the
 * top margin on the opening field of a form body.
 */
defineProps<{
  label: string
  hint?: string
  for?: string
  first?: boolean
}>()
</script>

<template>
  <div class="ui-fld" :class="{ 'ui-fld--first': first }">
    <label class="ui-fld-label" :for="$props.for">
      {{ label }} <span v-if="hint" class="ui-fld-hint">({{ hint }})</span>
    </label>
    <slot />
  </div>
</template>

<style scoped>
.ui-fld {
  margin-top: 14px;
}
.ui-fld--first {
  margin-top: 0;
}
.ui-fld-label {
  display: block;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--soft);
  margin: 0 0 6px;
}
.ui-fld-hint {
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  color: var(--soft);
}
</style>
