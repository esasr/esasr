import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'
import ReadingNav from '../src/components/ReadingNav.vue'

describe('reading navigation', () => {
  let wrapper: VueWrapper
  let sections: HTMLElement[]
  let scrollFrame: FrameRequestCallback | undefined
  let secondTop: number
  let reduced: boolean
  const disconnect = vi.fn()
  const jump = vi.fn()
  beforeEach(() => {
    secondTop = 900
    reduced = false
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect = disconnect })
    vi.stubGlobal('requestAnimationFrame', (fn: FrameRequestCallback) => { scrollFrame = fn; return 1 })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    vi.stubGlobal('matchMedia', () => ({ matches: reduced }))
    vi.spyOn(HTMLElement.prototype, 'scrollIntoView').mockImplementation(jump)
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    Object.defineProperty(window, 'scrollY', { configurable: true, value: 0 })
    Object.defineProperty(document.documentElement, 'scrollHeight', { configurable: true, value: 2400 })
    sections = ['abstract', 'network'].map(id => {
      const el = document.createElement('section')
      el.id = id
      el.tabIndex = -1
      el.getBoundingClientRect = () => ({ top: id === 'abstract' ? 0 : secondTop }) as DOMRect
      document.body.append(el)
      return el
    })
    wrapper = mount(ReadingNav, {
      props: { sections: [{ id: 'abstract', label: '摘要' }, { id: 'network', label: '关系图' }] },
      global: { plugins: [createI18n({ legacy: false, locale: 'zh' })], stubs: { MotionIcon: true } },
      attachTo: document.body,
    })
  })
  afterEach(() => { wrapper.unmount(); sections.forEach(el => el.remove()); vi.unstubAllGlobals(); vi.clearAllMocks() })

  it('tracks the section crossing the sticky reading boundary', async () => {
    expect(wrapper.get('[href="#abstract"]').attributes('aria-current')).toBe('location')
    secondTop = 80
    Object.defineProperty(window, 'scrollY', { configurable: true, value: 800 })
    window.dispatchEvent(new Event('scroll'))
    scrollFrame?.(0)
    await nextTick()
    expect(wrapper.get('[href="#network"]').attributes('aria-current')).toBe('location')
    expect(wrapper.get('.reading-progress').attributes('style')).not.toContain('scaleX(0)')
  })

  it('uses smooth explicit navigation and transfers keyboard focus', async () => {
    await wrapper.get('[href="#network"]').trigger('click')
    expect(jump).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
    expect(document.activeElement?.id).toBe('network')
  })

  it('respects reduced motion for navigation and back to top', async () => {
    reduced = true
    await wrapper.get('[href="#network"]').trigger('click')
    expect(jump).toHaveBeenCalledWith({ behavior: 'auto', block: 'start' })
    await wrapper.get('button').trigger('click')
    expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'auto' })
  })

  it('disconnects size observers when leaving the page', () => {
    wrapper.unmount()
    expect(disconnect).toHaveBeenCalled()
  })
})
