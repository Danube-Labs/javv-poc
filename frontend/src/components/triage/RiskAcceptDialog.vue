<script setup lang="ts">
/**
 * Scoped risk-accept (prototype `RiskAcceptDialog` on tokens) — creates an IMMUTABLE decision
 * (D40: edits later are revoke+new; `expiry` can never change). Scope chips are seeded from the
 * finding being viewed (its image and namespaces); empty scope = cluster-wide, and the blast
 * radius line says so before the operator commits. `apply_both_scanners` is D22's pinned
 * semantics — a scanner-specific decision names its scanner.
 */
import { computed, ref } from 'vue'

import { createApiV1DecisionsPost } from '@/api/generated'
import AppIcon from '@/components/ui/AppIcon.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import { useApi } from '@/composables/useApi'
import { logger } from '@/lib/logger'
import type { FindingRow } from '@/stores/findings'

const props = defineProps<{ cveId: string; finding: FindingRow }>()
const emit = defineEmits<{ close: []; created: [] }>()
const { withGlobals } = useApi()

const image = computed(() => `${props.finding.image_repo}${props.finding.tag ? ':' + props.finding.tag : ''}`)
const namespaces = computed(() =>
  Array.isArray(props.finding.namespaces) ? (props.finding.namespaces as string[]) : [],
)

const nsSel = ref<Set<string>>(new Set())
const imgSel = ref<Set<string>>(new Set())
const applyTo = ref<'both' | 'trivy' | 'grype'>('both')
const expiry = ref('')
const justification = ref('')
const submitting = ref(false)
const error = ref<string | null>(null)

function toggle(set: Set<string>, v: string) {
  if (set.has(v)) set.delete(v)
  else set.add(v)
}
const clusterWide = computed(() => nsSel.value.size === 0 && imgSel.value.size === 0)
const valid = computed(() => justification.value.trim().length > 0)

async function submit() {
  if (!valid.value || submitting.value) return
  submitting.value = true
  error.value = null
  const globals = withGlobals()
  const response = await createApiV1DecisionsPost({
    body: {
      type: 'risk_accepted',
      cve_id: props.cveId,
      scope: { namespaces: [...nsSel.value], images: [...imgSel.value] },
      apply_both_scanners: applyTo.value === 'both',
      ...(applyTo.value === 'both' ? {} : { scanner: applyTo.value }),
      justification: justification.value.trim(),
      ...(expiry.value ? { expiry: expiry.value } : {}),
      cluster_id: globals.cluster_id,
    },
  })
  submitting.value = false
  if (response.response?.ok) {
    logger.info('decision_created', { cve_id: props.cveId, type: 'risk_accepted' })
    emit('created')
    emit('close')
  } else {
    error.value =
      response.response?.status === 403
        ? 'Risk-accept needs the can_accept_audit_final capability.'
        : 'Could not create the decision — check the backend connection.'
    logger.warn('decision_create_failed', { status: response.response?.status })
  }
}

</script>

<template>
  <ModalShell title="Risk-accept this CVE" :subtitle="cveId" :width="560" @close="emit('close')">
      <div>
        <div class="ra-anchor">
          <span class="mono-cell strong">{{ cveId }}</span>
          <span class="ra-anchor-note">A decision anchors on the CVE + scope, so a package bump auto-inherits it.</span>
        </div>

        <label class="fld-label">Scope · namespaces <span class="fld-opt">(none selected = cluster-wide)</span></label>
        <div class="ra-chips">
          <span v-if="namespaces.length === 0" class="ra-none">no namespaces on this finding</span>
          <button
            v-for="ns in namespaces"
            :key="ns"
            type="button"
            class="ra-chip"
            :class="{ 'ra-chip-on': nsSel.has(ns) }"
            @click="toggle(nsSel, ns)"
          >
            {{ ns }}
          </button>
        </div>

        <label class="fld-label">Scope · images</label>
        <div class="ra-chips">
          <button
            type="button"
            class="ra-chip mono-cell"
            :class="{ 'ra-chip-on': imgSel.has(image) }"
            @click="toggle(imgSel, image)"
          >
            {{ image }}
          </button>
        </div>

        <div class="ra-blast">
          <AppIcon name="layers" :size="14" />
          <span>
            Blast radius:
            <b v-if="clusterWide">cluster-wide, every image</b>
            <b v-else>{{ imgSel.size }} image(s) + {{ nsSel.size }} namespace(s)</b>
            <em v-if="clusterWide || nsSel.size > 0"> · namespace/cluster scope auto-applies to NEW matching findings</em>
            <em v-else> · image scope does not cascade to new images</em>
          </span>
        </div>

        <div class="fld-2">
          <div>
            <label class="fld-label" for="ra-expiry">Expiry <span class="fld-opt">(immutable — change = revoke + new)</span></label>
            <input id="ra-expiry" v-model="expiry" class="fld" type="date" />
          </div>
          <div>
            <label class="fld-label">Apply to</label>
            <div class="seg">
              <button
                v-for="opt in (['both', 'trivy', 'grype'] as const)"
                :key="opt"
                type="button"
                class="seg-opt"
                :class="{ 'seg-on': applyTo === opt }"
                @click="applyTo = opt"
              >
                {{ opt === 'both' ? 'Both scanners' : opt + ' only' }}
              </button>
            </div>
          </div>
        </div>

        <label class="fld-label" for="ra-just">Justification (required)</label>
        <textarea
          id="ra-just"
          v-model="justification"
          class="fld"
          rows="3"
          placeholder="Why is this risk acceptable, and for how long?"
        />

        <p class="ra-note">
          <AppIcon name="info" :size="12" />
          Decisions are immutable. Editing later revokes and re-creates; the old one stays in history.
        </p>
        <p v-if="error" class="ra-error" role="alert">{{ error }}</p>
      </div>

      <template #actions>
        <button type="button" class="btn-ghost" @click="emit('close')">Cancel</button>
        <button type="button" class="btn-primary" :disabled="!valid || submitting" @click="submit">
          {{ submitting ? 'Creating…' : 'Create decision' }}
        </button>
      </template>
  </ModalShell>
</template>

<style scoped>
.ra-anchor {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-sm);
  padding: 9px 12px;
  margin-bottom: 4px;
}
.ra-anchor-note {
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.4;
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
.fld-opt {
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  color: var(--soft);
}
.ra-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ra-none {
  font-size: var(--text-sm);
  color: var(--soft);
}
.ra-chip {
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: var(--r-chip);
  padding: 5px 10px;
  font-size: var(--text-control);
  font-family: var(--font-ui);
  color: var(--ink);
  cursor: default;
}
.ra-chip:hover {
  border-color: var(--control-hover-line);
}
.ra-chip-on {
  border-color: var(--coral);
  background: var(--dd-on-bg);
  box-shadow: inset 0 0 0 1px var(--coral);
}
.ra-blast {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 12px;
  font-size: var(--text-sm);
  color: var(--ink);
  background: var(--panel);
  border-radius: var(--r-sm);
  padding: 9px 11px;
  line-height: 1.45;
}
.ra-blast svg {
  flex: none;
  margin-top: 1px;
  color: var(--teal);
}
.ra-blast em {
  font-style: normal;
  color: var(--soft);
}
.fld-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
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
.seg {
  display: inline-flex;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--panel);
}
.seg-opt {
  border: 0;
  border-radius: 5px;
  background: var(--card);
  padding: 7px 10px;
  font-size: var(--text-sm);
  font-family: var(--font-ui);
  color: var(--ink);
  cursor: default;
}
.seg-on {
  background: var(--dd-on-bg);
  color: var(--coral-text);
  box-shadow: inset 0 0 0 1px var(--coral);
  font-weight: 600;
}
.ra-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 12px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.45;
}
.ra-note svg {
  flex: none;
}
.ra-error {
  margin: 8px 0 0;
  font-size: var(--text-sm);
  color: var(--health-down-fg);
}
.mono-cell {
  font-family: var(--font-mono);
}
.strong {
  font-weight: 700;
}
.btn-mini {
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: var(--r-sm);
  padding: 3px 8px;
  font-size: var(--text-sm);
  color: var(--ink);
  cursor: default;
}
.btn-ghost,
.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border-radius: var(--r-sm);
  padding: 8px 14px;
  font-size: var(--text-control);
  font-family: var(--font-ui);
  font-weight: 600;
  cursor: default;
}
.btn-ghost {
  border: 1px solid var(--line);
  background: var(--card);
  color: var(--ink);
}
.btn-primary {
  border: 1px solid var(--coral-d);
  background: var(--coral);
  color: var(--kev-fg);
}
.btn-primary:hover:not(:disabled) {
  background: var(--coral-d);
}
.btn-primary:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
</style>
