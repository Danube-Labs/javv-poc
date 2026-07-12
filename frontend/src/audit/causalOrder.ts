/**
 * Causal display order for one page of audit events (M9d DoD, D38/H8 + D40/H-r3): the wire
 * order is the walk contract `(@timestamp, event_id)`, but SAME-FIELD edits of the same entity
 * must read by `revision` — a retried write can land two rows in the same millisecond with
 * event_ids that shuffle the true sequence. `revision` is the entity's resulting CAS version,
 * so it IS the causal sequence; everything else keeps the wire tiebreak.
 */
export interface CausalKey {
  '@timestamp': string
  event_id: string
  entity_id?: string | null
  field?: string | null
  revision?: number | null
}

export function causalOrder<E extends CausalKey>(events: readonly E[], order: 'asc' | 'desc' = 'desc'): E[] {
  const dir = order === 'asc' ? 1 : -1
  return [...events].sort((a, b) => {
    if (a['@timestamp'] !== b['@timestamp']) return a['@timestamp'] < b['@timestamp'] ? -dir : dir
    const sameField =
      a.entity_id != null && a.entity_id === b.entity_id && a.field != null && a.field === b.field
    if (sameField && typeof a.revision === 'number' && typeof b.revision === 'number' && a.revision !== b.revision)
      return (a.revision - b.revision) * dir
    if (a.event_id === b.event_id) return 0
    return a.event_id < b.event_id ? -dir : dir
  })
}
