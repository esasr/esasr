import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { vReveal } from '../src/directives/reveal'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
describe('scroll reveal', () => {
  it('never hides content when reduced motion is enabled', () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true }))
    const observe = vi.fn()
    vi.stubGlobal('IntersectionObserver', class { observe = observe })
    const wrapper = mount({ directives: { reveal: vReveal }, template: '<article v-reveal>Readable paper</article>' })
    expect(wrapper.text()).toBe('Readable paper')
    expect(wrapper.attributes('style')).toBeUndefined()
    expect(observe).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('animates once on intersection and releases resources', () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false }))
    let callback: IntersectionObserverCallback
    const disconnect = vi.fn()
    const cancel = vi.fn()
    const animate = vi.spyOn(HTMLElement.prototype, 'animate').mockReturnValue({ cancel } as unknown as Animation)
    vi.stubGlobal('IntersectionObserver', class {
      constructor(cb: IntersectionObserverCallback) { callback = cb }
      observe() {}
      disconnect = disconnect
    })
    const wrapper = mount({ directives: { reveal: vReveal }, template: '<article v-reveal>Readable paper</article>' })
    callback!([{ isIntersecting: true }] as IntersectionObserverEntry[], {} as IntersectionObserver)
    expect(animate).toHaveBeenCalledOnce()
    expect(disconnect).toHaveBeenCalledOnce()
    wrapper.unmount()
    expect(cancel).toHaveBeenCalledOnce()
  })
})
