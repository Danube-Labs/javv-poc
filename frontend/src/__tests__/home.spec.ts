import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import PlaceholderView from '@/views/PlaceholderView.vue'

describe('PlaceholderView', () => {
  it('names the screen and its owning bolt', () => {
    const wrapper = mount(PlaceholderView, { props: { title: 'Findings', bolt: 'M9b' } })
    expect(wrapper.find('h1').text()).toBe('Findings')
    expect(wrapper.text()).toContain('M9b')
  })
})
