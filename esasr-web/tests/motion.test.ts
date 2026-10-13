import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import MotionIcon from '../src/components/MotionIcon.vue'
import LordFeedback from '../src/components/LordFeedback.vue'

vi.mock('morphicons/vue', () => ({ MorphIcon: { props: ['icon', 'size', 'reducedMotion'], template: '<svg :width="size" :height="size"><path :d="icon" /></svg>' } }))
vi.mock('@lordicon/element', () => ({ defineElement: vi.fn() }))
const motion = ref('no-preference')
vi.mock('@vueuse/core', () => ({ usePreferredReducedMotion: () => motion }))
afterEach(() => { motion.value = 'no-preference' })

describe('motion icons', () => {
  it('keeps a fixed optical box and passes the user motion policy', async () => {
    const wrapper = mount(MotionIcon, { props: { name: 'bookmark', size: 18 } })
    const path = wrapper.get('path').attributes('d')
    expect(wrapper.attributes('style')).toContain('--icon-size: 18px')
    expect(wrapper.findComponent({ name: 'MorphIcon' }).exists() || wrapper.find('svg').exists()).toBe(true)
    await wrapper.setProps({ name: 'check' })
    expect(wrapper.get('path').attributes('d')).not.toBe(path)
    expect(wrapper.get('svg').attributes('width')).toBe('18')
    wrapper.unmount()
  })

  it('keeps a static fallback until the locally served Lordicon is ready, and on error', async () => {
    const wrapper = mount(LordFeedback, { props: { active: true } })
    await flushPromises()
    expect(wrapper.findComponent(MotionIcon).exists()).toBe(true)
    expect(wrapper.get('lord-icon').attributes('src')).toBe('/icons/lordicon/puzzle.json')
    expect(wrapper.get('lord-icon').attributes('trigger')).toBe('loop(1200)')
    await wrapper.get('lord-icon').trigger('ready')
    expect(wrapper.findComponent(MotionIcon).exists()).toBe(false)
    await wrapper.get('lord-icon').trigger('error')
    expect(wrapper.findComponent(MotionIcon).exists()).toBe(true)
    wrapper.unmount()
  })

  it('renders only a static illustration when reduced motion is requested', async () => {
    motion.value = 'reduce'
    const wrapper = mount(LordFeedback, { props: { active: true } })
    await flushPromises()
    expect(wrapper.find('lord-icon').exists()).toBe(false)
    expect(wrapper.findComponent(MotionIcon).exists()).toBe(true)
    wrapper.unmount()
  })
})
