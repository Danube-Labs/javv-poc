/**
 * The Data inspector's index list (issue 652): a long name truncates in the middle, but the
 * button's text, which screen readers announce and the e2e smoke reads, stays the full name, a
 * space, then the document count. The full name is also the row's title.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import InspectRail from '@/components/system/InspectRail.vue'

const LONG = 'top_queries-2026.10.01-59460'

describe('InspectRail index rows', () => {
  const rail = () =>
    mount(InspectRail, {
      props: {
        groups: { history: [{ pattern: 'javv-finding-occurrences-*', docs: 29 }], state: [{ pattern: LONG, docs: 117 }], system: [] },
        activePattern: '',
        failed: false,
      },
    })

  it("reads as the full name, a space, then the count", () => {
    const texts = rail()
      .findAll('button.idx')
      .map((b) => b.text())
    expect(texts).toEqual(['javv-finding-occurrences-* 29', `${LONG} 117`])
  })

  it('carries the full name in the title, split for middle truncation', () => {
    const name = rail().findAll('.idx-name')[1]!
    expect(name.attributes('title')).toBe(LONG)
    expect(name.find('.idx-tail').text()).toBe('0.01-59460')
  })
})
