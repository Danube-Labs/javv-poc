<script setup lang="ts">
/**
 * The settings save/discard footer (prototype `SaveBar`) — appended to editable panels ONLY
 * (§13: read-only sections carry no save bar). Consumers own dirty/valid/busy; the bar owns
 * the copy and the disabled contract.
 */
import UiButton from '@/components/ui/UiButton.vue'

defineProps<{ dirty: boolean; invalid?: boolean; busy?: boolean }>()
const emit = defineEmits<{ save: []; discard: [] }>()
</script>

<template>
  <div class="save-bar" :class="{ 'save-bar-on': dirty }">
    <span class="save-msg">{{ dirty ? 'You have unsaved changes' : 'All changes saved' }}</span>
    <div class="save-actions">
      <UiButton variant="ghost" :disabled="!dirty || busy" @click="emit('discard')">
        Discard
      </UiButton>
      <UiButton variant="primary" :disabled="!dirty || invalid || busy" @click="emit('save')">
        {{ busy ? 'Saving…' : 'Save changes' }}
      </UiButton>
    </div>
  </div>
</template>

<style scoped>
.save-bar {
  margin-top: 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 13px 18px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 11px;
  box-shadow: var(--shadow);
}
.save-msg {
  font-size: var(--text-mono-cell);
  font-family: var(--font-ui);
  color: var(--soft);
  font-weight: 500;
}
.save-bar-on {
  border-color: var(--save-dirty-line);
  background: var(--save-dirty-bg);
}
.save-bar-on .save-msg {
  color: var(--coral-text);
}
.save-actions {
  display: flex;
  gap: 10px;
}
</style>
