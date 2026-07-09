/**
 * Pure FE mirror of the FR-7 triage rules (the server's state machine is the authority —
 * backend/triage/state_machine.py): stale is system-only, resolved is manual, and the CISA-five
 * vex_justification is required iff the target is not_affected and rejected otherwise. The UI
 * uses this to disable Save and explain WHY before the server would 422.
 */

/** Human-selectable targets in the panel. risk_accepted is set by a scoped DECISION, never here. */
export const PANEL_TARGETS = [
  { state: 'open', label: 'Open' },
  { state: 'acknowledged', label: 'Acknowledge' },
  { state: 'not_affected', label: 'Not affected' },
  { state: 'resolved', label: 'Resolve' },
] as const

/** CISA five; `maps` mirrors the prototype's chips — the first two ARE "false positive". */
export const CISA_JUSTIFICATIONS = [
  { id: 'component_not_present', label: 'Component not present', maps: 'False positive' },
  { id: 'vulnerable_code_not_present', label: 'Vulnerable code not present', maps: 'False positive' },
  { id: 'vulnerable_code_not_in_execute_path', label: 'Code not in execute path', maps: 'Not exploitable' },
  {
    id: 'vulnerable_code_cannot_be_controlled_by_adversary',
    label: 'Code not adversary-controllable',
    maps: 'Not exploitable',
  },
  { id: 'inline_mitigations_already_exist', label: 'Inline mitigations exist', maps: 'Not exploitable' },
] as const

export interface TriageDraft {
  currentState: string
  targetState: string | null
  vexJustification: string | null
  notes: string
  assignee: string | null
}

export interface TriagePatchBody {
  state?: string
  vex_justification?: string
  assignee?: string
  notes?: string
}

/**
 * Draft → PATCH body, or a user-facing reason the draft is not saveable.
 * Mirrors the server rules; a null return for both means "nothing to save".
 */
export function buildTriagePatch(d: TriageDraft): { body: TriagePatchBody | null; error: string | null } {
  const stateChanged = d.targetState !== null && d.targetState !== d.currentState
  if (d.targetState === 'stale') {
    return { body: null, error: 'stale is system-set — it clears when the scanner reports again' }
  }
  if (stateChanged && d.targetState === 'not_affected' && !d.vexJustification) {
    return { body: null, error: 'not_affected requires a justification (CISA five)' }
  }
  const body: TriagePatchBody = {}
  if (stateChanged && d.targetState) {
    body.state = d.targetState
    if (d.targetState === 'not_affected' && d.vexJustification) {
      body.vex_justification = d.vexJustification // only ever sent WITH the state change
    }
  }
  if (d.notes.trim()) body.notes = d.notes.trim()
  if (d.assignee !== null) body.assignee = d.assignee
  if (Object.keys(body).length === 0) return { body: null, error: null }
  return { body, error: null }
}
