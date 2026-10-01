/**
 * Which guide section is in view, for the table of contents' active row: the first section whose
 * top has crossed the upper third of the viewport. Observes the rendered section ids once mounted.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { GUIDE_SECTIONS, type GuideSectionId } from '@/about/guide'

export function useActiveSection() {
  const active = ref<GuideSectionId | null>(null)
  let observer: IntersectionObserver | null = null
  const visible = new Set<GuideSectionId>()

  onMounted(() => {
    if (typeof IntersectionObserver === 'undefined') return
    observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          const id = e.target.id as GuideSectionId
          if (e.isIntersecting) visible.add(id)
          else visible.delete(id)
        }
        active.value = GUIDE_SECTIONS.find((s) => visible.has(s.id))?.id ?? active.value
      },
      { rootMargin: '0px 0px -66% 0px' },
    )
    for (const s of GUIDE_SECTIONS) {
      const el = document.getElementById(s.id)
      if (el) observer.observe(el)
    }
  })
  onBeforeUnmount(() => observer?.disconnect())

  return active
}
