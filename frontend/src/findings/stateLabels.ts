/**
 * What a finding state is CALLED on screen. One map, read by the state pill, the filter rail
 * and the filter pills alike (issue 674): the rail used to print the stored value
 * (`not_affected`) beside a pill that said "Not affected".
 */
export const STATE_LABELS: Record<string, string> = {
  open: 'Open',
  stale: 'Stale',
  acknowledged: 'Acknowledged',
  not_affected: 'Not affected',
  risk_accepted: 'Risk accepted',
  resolved: 'Resolved',
}

/** The display name of a state; an unknown value falls back to itself, never to blank. */
export const stateLabel = (state: string): string => STATE_LABELS[state] ?? state
