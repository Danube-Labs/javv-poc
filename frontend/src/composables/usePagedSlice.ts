/**
 * Client-side display paging over an already-fetched, bounded row set (the
 * contributors-leaderboard model): the server returns the capped board once, the UI walks it
 * in GridPager-sized slices. NOT for server cursor paging — that's the findings/audit grid
 * stores' job. Feed it a getter so the slice resets to page 0 whenever the rows change.
 */
import { computed, ref, watch, type Ref } from 'vue'

export function usePagedSlice<T>(rows: () => readonly T[], initialSize = 10) {
  const page: Ref<number> = ref(0)
  const size: Ref<number> = ref(initialSize)
  watch(rows, () => (page.value = 0))
  const shown = computed(() => rows().slice(page.value * size.value, (page.value + 1) * size.value))
  const hasNext = computed(() => (page.value + 1) * size.value < rows().length)
  function setSize(next: number) {
    size.value = next
    page.value = 0
  }
  return { page, size, shown, hasNext, setSize }
}
