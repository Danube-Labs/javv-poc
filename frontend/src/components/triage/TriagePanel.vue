<script setup lang="ts">
/**
 * The triage aside (prototype `.triage` on tokens) — FR-7 two-field VEX. Read-only when the
 * user lacks can_triage, and when viewing history (T<now: reconstructed state is not editable).
 * risk_accepted and stale render explainer blocks instead of buttons; the presence explainer
 * (fixed vs stale) is kept verbatim from the prototype. Save emits the validated PATCH body —
 * the parent owns the network call and conflict surfacing.
 */
import { computed, ref, watch } from 'vue'

import StateTag from '@/components/chips/StateTag.vue'
import TriageStateControl from '@/components/triage/TriageStateControl.vue'
import VexJustificationPicker from '@/components/triage/VexJustificationPicker.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { buildTriagePatch, type TriagePatchBody } from '@/findings/triageRules'
import type { FindingRow } from '@/stores/findings'

const props = defineProps<{
  finding: FindingRow
  canTriage: boolean
  canAcceptFinal: boolean
  historical: boolean
  saving: boolean
  error: string | null
  currentUser: string | null
}>()
const emit = defineEmits<{ save: [body: TriagePatchBody]; riskAccept: [] }>()

const target = ref<string | null>(null)
const vexJustification = ref<string | null>(null)
const notes = ref('')
const assignee = ref<string | null>(null)

watch(
  () => props.finding.finding_key,
  () => {
    target.value = null
    vexJustification.value = null
    notes.value = ''
    assignee.value = null
  },
)

const locked = computed(() => !props.canTriage || props.historical)
const shownState = computed(() => target.value ?? props.finding.state)
const draft = computed(() =>
  buildTriagePatch({
    currentState: props.finding.state,
    targetState: target.value,
    vexJustification: vexJustification.value,
    notes: notes.value,
    assignee: assignee.value,
  }),
)

function pickState(s: string) {
  if (locked.value) return
  target.value = s
  if (s !== 'not_affected') vexJustification.value = null
}
function save() {
  if (draft.value.body) emit('save', draft.value.body)
}
</script>

<template>
  <aside class="triage">
    <div class="triage-head">
      <AppIcon name="shield" :size="16" /><span>Triage</span>
      <StateTag class="head-state" :state="finding.state" />
    </div>
    <div class="triage-body">
      <div v-if="historical" class="triage-locked">
        <AppIcon name="clock" :size="13" />
        Viewing history — reconstructed state is read-only. Return to now to triage.
      </div>
      <div v-else-if="!canTriage" class="triage-locked">
        <AppIcon name="key" :size="13" />
        Read-only — you don't hold <b>can_triage</b>. Ask an Operator or Security Lead.
      </div>

      <label class="fld-label">Assigned to</label>
      <div class="assignee-row">
        <span class="assignee-val">{{ assignee ?? finding.assignee ?? 'unassigned' }}</span>
        <UiButton
          v-if="currentUser"
          :disabled="locked || (assignee ?? finding.assignee) === currentUser"
          @click="assignee = currentUser"
        >
          Assign to me
        </UiButton>
      </div>

      <label class="fld-label">State · VEX lifecycle</label>
      <TriageStateControl :current="finding.state" :target="target" :disabled="locked" @select="pickState" />

      <div v-if="shownState === 'not_affected'" class="vex-block">
        <label class="fld-label">Justification · CISA five (required)</label>
        <VexJustificationPicker
          :selected="vexJustification"
          :disabled="locked"
          @select="(id) => (vexJustification = id)"
        />
      </div>

      <div v-if="finding.state === 'risk_accepted'" class="ro-state ro-risk">
        <AppIcon name="shield" :size="13" />
        <div>
          <b>Set by a scoped decision</b>
          <span>Risk-accept isn't toggled here — it comes from a decision (scope + approver + expiry). Manage it below.</span>
        </div>
      </div>
      <div v-if="finding.state === 'stale'" class="ro-state ro-stale">
        <AppIcon name="clock" :size="13" />
        <div>
          <b>System-set · scanner went silent</b>
          <span>The scanner stopped reporting this finding; data may be old. A human state change overrides it.</span>
        </div>
      </div>

      <div class="presence-note">
        <span class="pn-row"><i class="pn-dot pn-fixed" /><b>Fixed</b>&nbsp;· absent from the latest scan → drops off the "now" grid immediately.</span>
        <span class="pn-row"><i class="pn-dot pn-stale" /><b>Stale</b>&nbsp;· scanner silent → still shown, flagged; presence unknown.</span>
      </div>

      <label class="fld-label" for="triage-notes">Note <span class="fld-opt">(escaped, never rendered as HTML)</span></label>
      <textarea
        id="triage-notes"
        v-model="notes"
        class="fld"
        rows="3"
        placeholder="Add context for the audit trail…"
        :disabled="locked"
      />

      <p v-if="draft.error" class="draft-error" role="alert">{{ draft.error }}</p>
      <p v-if="error" class="draft-error" role="alert">{{ error }}</p>

      <UiButton
        v-if="canAcceptFinal"
        variant="ghost"
        block
        class="btn-gap"
        :disabled="historical"
        @click="emit('riskAccept')"
      >
        <AppIcon name="shield" :size="14" />Risk-accept this CVE…
      </UiButton>
      <UiButton
        variant="primary"
        block
        class="btn-gap"
        :disabled="locked || saving || !draft.body"
        @click="save"
      >
        {{ saving ? 'Saving…' : 'Save to audit trail' }}
      </UiButton>
      <p class="triage-foot">
        <AppIcon name="clock" :size="11" />Every action records who &amp; when. Deadlines absolute, 24h.
      </p>
    </div>
  </aside>
</template>

<style scoped>
.triage {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  position: sticky;
  top: 12px;
  overflow: hidden;
}
.triage-head {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--line2);
  font-weight: 600;
  font-size: var(--text-card-title);
  background: var(--panel);
}
.triage-head svg {
  color: var(--coral);
}
.head-state {
  margin-left: auto;
}
.triage-body {
  padding: 16px;
}
.triage-locked {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-sm);
  color: var(--hist-fg);
  background: var(--hist-bg);
  border: 1px solid var(--hist-line);
  border-radius: var(--r-sm);
  padding: 8px 10px;
  margin-bottom: 12px;
  line-height: 1.45;
}
.triage-locked svg {
  flex: none;
}
.fld-label {
  display: block;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--soft);
  margin: 14px 0 6px;
}
.fld-label:first-of-type {
  margin-top: 0;
}
.fld-opt {
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  color: var(--soft);
}
.assignee-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.assignee-val {
  font-size: var(--text-body);
  color: var(--ink);
}
.vex-block {
  margin-top: 2px;
}
.ro-state {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  border-radius: var(--r-sm);
  padding: 10px 12px;
  margin-top: 8px;
  font-size: var(--text-sm);
  line-height: 1.45;
}
.ro-state svg {
  flex: none;
  margin-top: 2px;
}
.ro-state b {
  display: block;
  font-size: var(--text-control);
  margin-bottom: 2px;
}
.ro-state span {
  color: var(--soft);
}
.ro-risk {
  background: var(--hist-bg);
  border: 1px solid var(--hist-line);
  color: var(--hist-fg);
}
.ro-stale {
  background: var(--state-stale-bg);
  border: 1px solid var(--state-stale-line);
  color: var(--state-stale-fg);
}
.presence-note {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin: 12px 0 4px;
  font-size: var(--text-sm);
  color: var(--ink);
  background: var(--panel);
  border-radius: var(--r-sm);
  padding: 9px 11px;
  line-height: 1.4;
}
.pn-row {
  display: flex;
  align-items: center;
  gap: 7px;
}
.pn-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
.pn-fixed {
  background: var(--state-resolved-fg);
}
.pn-stale {
  background: var(--state-stale-fg);
}
.fld {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 8px 10px;
  font-family: var(--font-ui);
  font-size: var(--text-mono-cell);
  color: var(--ink);
  background: var(--card);
  outline: none;
  resize: vertical;
  box-sizing: border-box;
}
.fld:focus {
  border-color: var(--coral);
}
.fld:disabled {
  background: var(--panel);
  color: var(--soft);
}
.draft-error {
  margin: 8px 0 0;
  font-size: var(--text-sm);
  color: var(--health-down-fg);
}
.btn-gap {
  margin-top: 8px;
}
.triage-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-facet-label);
  color: var(--soft);
  margin: 10px 0 0;
  line-height: 1.4;
}
.triage-foot svg {
  flex: none;
}
</style>
