<script setup lang="ts">
/**
 * Edit a standing risk-acceptance (M9d slice 4) — PATCH /decisions/{id}, the server's ATOMIC
 * revoke+new (D40: one effective_at + operation_id; the old row strikes through, a new
 * decision_id appears). Only the human-judgment fields are editable here — justification and
 * expiry; scope/scanner re-targeting is a different decision, made from the finding.
 */
import { computed, ref } from 'vue'

import { editApiV1DecisionsDecisionIdPatch } from '@/api/generated'
import type { ApprovalRow } from '@/approvals/viewModel'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import { logger } from '@/lib/logger'

const props = defineProps<{ decision: ApprovalRow }>()
const emit = defineEmits<{ close: []; edited: [] }>()

const justification = ref(props.decision.justification)
const expiry = ref(props.decision.expiry ? props.decision.expiry.slice(0, 10) : '')
const submitting = ref(false)
const error = ref<string | null>(null)

const dirty = computed(
  () =>
    justification.value.trim() !== props.decision.justification ||
    expiry.value !== (props.decision.expiry ? props.decision.expiry.slice(0, 10) : ''),
)
const valid = computed(() => justification.value.trim().length > 0 && dirty.value)

async function submit() {
  if (!valid.value || submitting.value) return
  submitting.value = true
  error.value = null
  const changes: Record<string, string> = {}
  if (justification.value.trim() !== props.decision.justification)
    changes.justification = justification.value.trim()
  if (expiry.value && expiry.value !== (props.decision.expiry ?? '').slice(0, 10))
    changes.expiry = expiry.value
  const response = await editApiV1DecisionsDecisionIdPatch({
    path: { decision_id: props.decision.decision_id },
    body: changes,
  })
  submitting.value = false
  if (response.response?.ok) {
    logger.info('decision_edited', { decision_id: props.decision.decision_id })
    emit('edited')
    emit('close')
  } else {
    error.value =
      response.response?.status === 409
        ? 'This decision was already revoked — refresh the queue.'
        : 'Could not apply the edit — check the backend connection.'
    logger.warn('decision_edit_failed', { status: response.response?.status })
  }
}
</script>

<template>
  <ModalShell
    title="Edit risk-acceptance"
    :subtitle="decision.cve_id"
    :width="520"
    @close="emit('close')"
  >
    <p class="ed-note">
      An edit is <b>revoke + new</b> (decisions are immutable): the current decision is
      revoked and a new one takes effect atomically, keeping the audit trail causal.
    </p>
    <UiField label="Justification" for="ed-just">
      <textarea id="ed-just" v-model="justification" class="fld ed-just" rows="4" />
    </UiField>
    <UiField label="Expiry" hint="empty keeps the current expiry" for="ed-expiry">
      <input id="ed-expiry" v-model="expiry" class="fld" type="date" />
    </UiField>
    <p v-if="error" class="ed-error" role="alert">{{ error }}</p>
    <template #actions>
      <UiButton variant="quiet" @click="emit('close')">Cancel</UiButton>
      <UiButton :disabled="!valid || submitting" @click="submit">
        {{ submitting ? 'Saving…' : 'Revoke + re-issue' }}
      </UiButton>
    </template>
  </ModalShell>
</template>

<style scoped>
.ed-note {
  margin: 0 0 12px;
  font-size: var(--text-sm);
  color: var(--soft);
}
.ed-just {
  resize: vertical;
}
.ed-error {
  margin: 10px 0 0;
  font-size: var(--text-sm);
  color: var(--health-down-fg);
}
</style>
