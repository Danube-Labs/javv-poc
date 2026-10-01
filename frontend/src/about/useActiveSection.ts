/**
 * Which guide section is in view, for "On this page": the last section whose top has crossed a
 * line near the top of the viewport, or the last section once the page can't scroll any
 * further (a short closing section never reaches the line). Recomputed on scroll and resize.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { GUIDE_SECTIONS, type GuideSectionId } from '@/about/guide'
import { HASH_SCROLL_TOP } from '@/system/hashScroll'

/**
 * The line sits just below where a section link lands, never a fraction of the viewport: on a
 * tall screen a third of the way down is past the start of the section after a short one, so
 * landing on Scans and freshness highlighted Images. 80px clears the landing and stays above
 * the next section, since every section's card is taller than that.
 */
export const SPY_LINE_PX = HASH_SCROLL_TOP + 80

export interface SectionTop<T extends string = string> {
  id: T
  top: number
}

/** The scroll-spy rule, pure: `tops` in page order, `line` in viewport pixels. */
export function activeAt<T extends string>(
  tops: readonly SectionTop<T>[],
  line: number,
  atBottom: boolean,
): T | null {
  if (tops.length === 0) return null
  if (atBottom) return tops[tops.length - 1]!.id
  let current = tops[0]!.id
  for (const t of tops) if (t.top <= line) current = t.id
  return current
}

export function useActiveSection() {
  const active = ref<GuideSectionId | null>(null)
  let frame = 0

  function measure() {
    frame = 0
    const tops = GUIDE_SECTIONS.flatMap((s) => {
      const el = document.getElementById(s.id)
      return el ? [{ id: s.id, top: el.getBoundingClientRect().top }] : []
    })
    const doc = document.documentElement
    const atBottom = window.scrollY > 0 && window.innerHeight + window.scrollY >= doc.scrollHeight - 2
    active.value = activeAt(tops, SPY_LINE_PX, atBottom)
  }
  function schedule() {
    if (!frame) frame = requestAnimationFrame(measure)
  }

  onMounted(() => {
    measure()
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('scroll', schedule)
    window.removeEventListener('resize', schedule)
    if (frame) cancelAnimationFrame(frame)
  })

  return active
}
