<script setup lang="ts">
/**
 * SLA policy panel (§13.3; prototype screens-config.jsx `sla` section): remediation days per
 * severity + the KEV override — GET open to any session, PUT gated `can_manage_settings` and
 * journaled with the full old/new policy (D17). Two spec-truths replace prototype copy: edits
 * apply IMMEDIATELY (the policy is read live per request — deadlines recompute, nothing is
 * "not rewritten"), and negligible/unknown carry NO SLA by ruling (tests/test_sla.py).
 * KEV is a DAYS window with no on/off toggle (D46 `kev_days`), not the prototype's hours+switch.
 */
import { computed, ref } from 'vue'

import { getSlaApiV1SettingsSlaGet, putSlaApiV1SettingsSlaPut } from '@/api/generated'
import type { SlaPolicy } from '@/api/generated'
import { client } from '@/api/client'
import AppIcon from '@/components/ui/AppIcon.vue'
import SaveBar from '@/components/settings/SaveBar.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import SettingsRow from '@/components/settings/SettingsRow.vue'
import SevChip from '@/components/chips/SevChip.vue'
import { logger } from '@/lib/logger'
import { useToastStore } from '@/stores/toast'

import {
  draftFromPolicy,
  isDirty,
  parseWindow,
  policyFromDraft,
  SLA_SEVERITY_ROWS,
  type SlaDraft,
} from './slaForm'

const toast = useToastStore()

const saved = ref<SlaPolicy | null>(null)
const draft = ref<SlaDraft | null>(null)
const loading = ref(true)
const failed = ref(false)
const busy = ref(false)

async function load() {
  loading.value = true
  const { data, response } = await getSlaApiV1SettingsSlaGet({ client })
  loading.value = false
  failed.value = !response?.ok
  if (failed.value) {
    logger.warn('sla_policy_load_failed', { status: response?.status })
    return
  }
  saved.value = (data as { sla: SlaPolicy }).sla
  draft.value = draftFromPolicy(saved.value)
}
void load()

const dirty = computed(() =>
  draft.value !== null && saved.value !== null ? isDirty(draft.value, saved.value) : false,
)
const invalid = computed(() => draft.value !== null && policyFromDraft(draft.value) === null)

const SAVE_FAILURE: Record<number, string> = {
  403: 'Saving needs the can_manage_settings capability.',
  422: 'The policy was rejected — every window must be a positive number of days.',
}

async function save() {
  if (draft.value === null) return
  const body = policyFromDraft(draft.value)
  if (body === null) return
  busy.value = true
  const { response } = await putSlaApiV1SettingsSlaPut({ client, body })
  busy.value = false
  if (!response?.ok) {
    logger.warn('sla_policy_save_failed', { status: response?.status })
    toast.error(
      SAVE_FAILURE[response?.status ?? 0] ?? 'Saving the SLA policy failed — nothing was changed.',
    )
    return
  }
  saved.value = body
  draft.value = draftFromPolicy(body)
  toast.success('SLA policy saved — deadlines recompute immediately')
}

function discard() {
  if (saved.value !== null) draft.value = draftFromPolicy(saved.value)
}
</script>

<template>
  <div>
    <SettingsCard
      title="SLA policy"
      subtitle="remediation deadlines per severity — drives the SLA column and overdue flags"
    >
      <div v-if="loading" class="skel skel-form" aria-busy="true" aria-label="Loading SLA policy" />

      <p v-else-if="failed" class="load-error" role="alert">
        SLA policy unavailable. Check the backend connection.
      </p>

      <template v-else-if="draft">
        <SettingsRow
          v-for="row in SLA_SEVERITY_ROWS"
          :key="row.key"
          :hint="
            row.key === 'critical_days'
              ? 'Clock starts when the finding first appears in a committed scan.'
              : undefined
          "
        >
          <template #label><SevChip :level="row.severity" /></template>
          <SettingsInput
            v-model="draft[row.key]"
            num
            unit="days"
            :invalid="parseWindow(draft[row.key]) === null"
            :id="`sla-${row.key}`"
          />
        </SettingsRow>
        <SettingsRow
          label="KEV override"
          hint="Known-exploited findings ignore the table above and get this tighter window. Fractions work — 0.5 is 12 hours."
        >
          <SettingsInput
            v-model="draft.kev_days"
            num
            unit="days"
            :invalid="parseWindow(draft.kev_days) === null"
            id="sla-kev_days"
          />
        </SettingsRow>
        <div class="sla-note">
          <AppIcon name="info" :size="13" />
          <span>
            Changes apply immediately — deadlines are computed live from this policy, existing
            findings included. <b>negligible</b> and <b>unknown</b> severities carry no SLA.
          </span>
        </div>
      </template>
    </SettingsCard>

    <SaveBar
      v-if="!loading && !failed"
      :dirty="dirty"
      :invalid="invalid"
      :busy="busy"
      @save="save"
      @discard="discard"
    />
  </div>
</template>

<style scoped>
/* prototype .ignore-best note grammar (quiet inset banner), ink prose per DESIGN.md §2 */
.sla-note {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: var(--text-sweep-strong);
  color: var(--ink);
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: 9px;
  padding: 9px 12px;
  line-height: 1.45;
  margin-top: 14px;
}
.sla-note svg {
  flex: none;
  color: var(--teal);
}
.load-error {
  margin: 14px 0 8px;
}
.skel-form {
  height: 280px;
  margin: 14px 0 8px;
  border-radius: var(--r-sm);
  background: linear-gradient(90deg, var(--line2) 25%, var(--panel) 50%, var(--line2) 75%);
  background-size: 200% 100%;
  animation: skel-shimmer 1.4s ease-in-out infinite;
}
@keyframes skel-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .skel-form {
    animation: none;
  }
}
</style>
