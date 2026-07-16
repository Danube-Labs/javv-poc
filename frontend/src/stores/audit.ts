/** Grid state for the audit table (M9d slice 1; SCREENS §10) — the same cursor-stack pager
 * contract as the findings grid: `cursors[i]` fetches page i (page 0 = null), no offset, no
 * random jumps; rows/total are the server's verbatim. Rows are the D32 stream, decorated at
 * read with the touched entity's identity (`finding`/`decision` sub-objects — null when the
 * doc aged out of the store or the event was a bulk marker). */
import { defineStore } from 'pinia'

export interface AuditEvent {
  event_id: string
  '@timestamp': string
  actor: string
  action: string
  entity_type: string
  entity_id: string
  finding_key?: string | null
  decision_id?: string | null
  field?: string | null
  field_type?: string | null
  old_value?: string | null
  new_value?: string | null
  new_value_json?: Record<string, unknown> | null
  revision?: number | null
  cluster_id?: string
  /** read-time decoration (M9d): the finding this event touched, null once aged out */
  finding?: {
    cve_id: string
    image_repo?: string | null
    image_digest?: string | null
    scanner?: string | null
    package_name?: string | null
    severity_canonical?: string | null
  } | null
  /** read-time decoration: the decision this event touched */
  decision?: {
    cve_id: string
    type?: string | null
    scanner?: string | null
    apply_both_scanners?: boolean | null
  } | null
}

export const useAuditStore = defineStore('audit', {
  state: () => ({
    rows: [] as AuditEvent[],
    total: 0,
    totalIsLowerBound: false,
    size: 25,
    page: 0,
    cursors: [null] as (string | null)[],
    nextCursor: null as string | null,
    loading: false,
    failed: false,
  }),
  getters: {
    hasPrev: (s) => s.page > 0,
    hasNext: (s) => s.nextCursor !== null,
    /** Cursor to fetch the CURRENT page with. */
    activeCursor: (s) => s.cursors[s.page] ?? null,
  },
  actions: {
    setResult(rows: AuditEvent[], total: { value: number; relation: string }, nextCursor: string | null) {
      this.rows = rows
      this.total = total.value
      this.totalIsLowerBound = total.relation !== 'eq'
      this.nextCursor = nextCursor
      if (nextCursor !== null) this.cursors[this.page + 1] = nextCursor
    },
    goNext() {
      if (this.nextCursor !== null) this.page += 1
    },
    goPrev() {
      if (this.page > 0) this.page -= 1
    },
    setSize(size: number) {
      this.size = size
      this.resetPaging()
    },
    /** Filters/globals changed or a cursor went stale — back to page 0, stack rebuilt. */
    resetPaging() {
      this.page = 0
      this.cursors = [null]
      this.nextCursor = null
    },
    /** Cluster or T switched — the held rows belong to another tenant/world; drop them so the
     * loading state shows instead of readable stale data while the new read is in flight. */
    clearResults() {
      this.rows = []
      this.total = 0
      this.totalIsLowerBound = false
      this.resetPaging()
    },
  },
})
