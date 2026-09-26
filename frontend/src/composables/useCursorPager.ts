/**
 * Cursor-stack paging for a server-paged table: the backend hands back an opaque
 * `next_cursor` per page, so going BACK means remembering the cursor that fetched each page
 * already seen. `cursors[i]` is the cursor that FETCHES page i; page 0's is always `null`.
 *
 * Owns the stack and nothing else: the caller fetches with `cursor.value`, reports the answer's
 * `next_cursor` through `landed()`, and refetches when `next()`/`prev()` say the page moved. A
 * changed query (filter, cluster, T, page size) must `reset()` — a stack from another query would
 * page through the wrong answer. Pairs with GridPager: `page`, `size`, `hasPrev`, `hasNext`.
 *
 * For a bounded row set the client already holds, use `usePagedSlice` instead.
 */
import { computed, ref } from 'vue'

export function useCursorPager(initialSize = 25) {
  const page = ref(0)
  const size = ref(initialSize)
  const cursors = ref<(string | null)[]>([null])
  const nextCursor = ref<string | null>(null)

  /** the cursor to send for the current page (`null` = the first page) */
  const cursor = computed(() => cursors.value[page.value] ?? null)
  const hasPrev = computed(() => page.value > 0)
  const hasNext = computed(() => nextCursor.value !== null)

  /** Record the answer for the current page. */
  function landed(next: string | null) {
    nextCursor.value = next
  }

  /** Step forward; true when the page moved and the caller must fetch. */
  function next(): boolean {
    if (nextCursor.value === null) return false
    cursors.value[page.value + 1] = nextCursor.value
    page.value += 1
    nextCursor.value = null // unknown until the new page lands
    return true
  }

  /** Step back; true when the page moved and the caller must fetch. */
  function prev(): boolean {
    if (page.value === 0) return false
    page.value -= 1
    nextCursor.value = null
    return true
  }

  function reset() {
    page.value = 0
    cursors.value = [null]
    nextCursor.value = null
  }

  function setSize(n: number) {
    size.value = n
    reset()
  }

  return { page, size, cursor, hasPrev, hasNext, landed, next, prev, reset, setSize }
}
