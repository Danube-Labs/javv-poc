<script setup lang="ts">
/**
 * The settings text/number input (prototype `.num-input`/`.text-input` + unit suffix) with the
 * full feedback contract (hover wash shift, focus, invalid) owned once. `unit` renders the
 * mono suffix ("days", "GB"); `num` narrows to the numeric width. Value stays a string —
 * parsing/validation is the consumer's form logic (contract guards live there).
 */
withDefaults(
  defineProps<{
    modelValue: string
    num?: boolean
    unit?: string
    invalid?: boolean
    id?: string
    disabled?: boolean
  }>(),
  { num: false, invalid: false },
)
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <span class="set-input-wrap">
    <input
      :id="id"
      class="set-input"
      :class="{ 'set-input--num': num, 'set-input--invalid': invalid }"
      :value="modelValue"
      :aria-invalid="invalid || undefined"
      :disabled="disabled"
      inputmode="decimal"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <span v-if="unit" class="set-input-unit">{{ unit }}</span>
  </span>
</template>

<style scoped>
.set-input-wrap {
  display: inline-flex;
  align-items: center;
  gap: 9px;
}
.set-input {
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 8px 11px;
  font-size: var(--text-mono-cell);
  font-family: var(--font-mono);
  color: var(--ink);
  background: var(--card);
  outline: none;
  width: 100%;
  transition:
    border-color var(--dur-quick) var(--ease-out),
    background var(--dur-quick) var(--ease-out);
}
.set-input--num {
  width: 88px;
}
.set-input:hover:not(:disabled) {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.set-input:focus {
  border-color: var(--coral);
  background: var(--card);
}
.set-input:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.set-input--invalid {
  border-color: var(--coral-d);
}
.set-input:disabled {
  color: var(--soft);
  background: var(--panel);
  cursor: not-allowed;
}
.set-input-unit {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--soft);
}
</style>
