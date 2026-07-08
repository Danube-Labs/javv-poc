import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import HomeView from '@/views/HomeView.vue'
import { SEVERITIES } from '@/styles/tokens'

describe('HomeView', () => {
  it('renders one chip per canonical severity', () => {
    const wrapper = mount(HomeView)
    const chips = wrapper.findAll('.sev-chip')
    expect(chips.map((c) => c.text())).toEqual([...SEVERITIES])
  })
})
