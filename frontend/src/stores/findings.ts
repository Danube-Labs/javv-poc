/**
 * Grid state for the findings table. The shipped M6 contract pages by cursor (PIT +
 * search_after) — there is no offset, so no random page jumps: the pager walks prev/next over a
 * cursor stack (`cursors[i]` = cursor that FETCHES page i; page 0 = null). Everything displayed
 * (rows, total) is the server's — nothing is counted or paged client-side.
 *
 * Cursors embed a PIT that the server expires after a while — a stale-cursor fetch fails and the
 * caller resets to page 0 (`resetPaging`).
 */
import { defineStore } from 'pinia'

import type { SortField, SortOrder } from '@/findings/buildFindingsQuery'

/** The findings-search row shape this bolt renders (subset of the server doc; B-2: only real fields). */
export interface FindingRow {
  finding_key: string
  cve_id: string
  scanner: string
  severity: string
  severity_canonical: string
  image_repo: string
  tag: string | null
  package_name: string
  installed_version: string | null
  fixed_version: string | null
  fixable: boolean
  epss: number | null
  kev: boolean
  ptype: string | null
  state: string
  disagree?: boolean
  assignee?: string | null
  overdue: boolean
  due_at: string | null
  [key: string]: unknown
}

export const useFindingsStore = defineStore('findings', {
  state: () => ({
    rows: [] as FindingRow[],
    total: 0,
    sort: 'severity_rank' as SortField,
    order: 'desc' as SortOrder,
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
    setResult(rows: FindingRow[], total: number, nextCursor: string | null) {
      this.rows = rows
      this.total = total
      this.nextCursor = nextCursor
      if (nextCursor !== null) this.cursors[this.page + 1] = nextCursor
    },
    goNext() {
      if (this.nextCursor !== null) this.page += 1
    },
    goPrev() {
      if (this.page > 0) this.page -= 1
    },
    setSort(sort: SortField) {
      // same column toggles direction; a new column starts desc (prototype behavior)
      this.order = this.sort === sort ? (this.order === 'desc' ? 'asc' : 'desc') : 'desc'
      this.sort = sort
      this.resetPaging()
    },
    setSize(size: number) {
      this.size = size
      this.resetPaging()
    },
    /** Filters/sort/size changed or a cursor went stale — back to page 0, stack rebuilt. */
    resetPaging() {
      this.page = 0
      this.cursors = [null]
      this.nextCursor = null
    },
  },
})
