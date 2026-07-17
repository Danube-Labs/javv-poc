<script setup lang="ts">
/**
 * "Save view" (M9f slice 4): names the CURRENT workbench — lens (negation included) + columns/
 * density/sort/window — and stores it server-side (C-6: durable, visible to every user). The
 * capture itself is computed by the owning screen; this dialog only names and posts it.
 */
import { computed, ref } from 'vue'

import { createViewApiV1ViewsPost, type ViewPreset, type ViewWorkbench } from '@/api/generated'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { presetSummary } from '@/findings/savedViews'
import { logger } from '@/lib/logger'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{ preset: ViewPreset; workbench: ViewWorkbench }>()
const toast = useToastStore()

const open = ref(false)
const name = ref('')
const description = ref('')
const saving = ref(false)

const summary = computed(() => presetSummary(FINDINGS_FIELDS, props.preset))

function show() {
  name.value = ''
  description.value = ''
  open.value = true
}

async function save() {
  const trimmed = name.value.trim()
  if (!trimmed) {
    toast.info('A view needs a name.')
    return
  }
  saving.value = true
  try {
    const { response } = await createViewApiV1ViewsPost({
      body: { name: trimmed, description: description.value.trim(), preset: props.preset, workbench: props.workbench },
    })
    if (response?.ok) {
      toast.success(`View “${trimmed}” saved`)
      open.value = false
    } else {
      logger.warn('view_save_failed', { status: response?.status })
      toast.error(response?.status === 422 ? 'The current lens is not storable as a view.' : 'Saving the view failed — try again.')
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <UiButton variant="control" @click="show">Save view</UiButton>
  <ModalShell v-if="open" title="Save this view" subtitle="Filters, columns and time window — reusable by everyone" :width="440" @close="open = false">
    <div class="svd-body">
      <p class="svd-summary">{{ summary }}</p>
      <UiField label="Name">
        <input v-model="name" maxlength="128" placeholder="e.g. Critical KEV backlog" @keydown.enter="save" />
      </UiField>
      <UiField label="Description (optional)">
        <input v-model="description" maxlength="1024" placeholder="What this lens is for" @keydown.enter="save" />
      </UiField>
      <div class="svd-actions">
        <UiButton variant="control" @click="open = false">Cancel</UiButton>
        <UiButton variant="primary" :disabled="saving" @click="save">Save view</UiButton>
      </div>
    </div>
  </ModalShell>
</template>

<style scoped>
.svd-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
}
.svd-summary {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--soft);
  font-style: italic;
}
.svd-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
