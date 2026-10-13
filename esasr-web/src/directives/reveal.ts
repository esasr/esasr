import type { ObjectDirective } from 'vue'

const observers = new WeakMap<HTMLElement, IntersectionObserver>()
const animations = new WeakMap<HTMLElement, Animation>()

/** Content stays visible if animation/observer APIs fail or motion is disabled. */
export const vReveal: ObjectDirective<HTMLElement> = {
  mounted(el) {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window) || !el.animate) return
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return
      observer.disconnect()
      observers.delete(el)
      if (matchMedia('(prefers-reduced-motion: reduce)').matches) return
      animations.set(el, el.animate(
        [{ opacity: .65, transform: 'translateY(6px)' }, { opacity: 1, transform: 'translateY(0)' }],
        { duration: 220, easing: 'cubic-bezier(.2,.7,.2,1)' },
      ))
    }, { threshold: .08 })
    observer.observe(el)
    observers.set(el, observer)
  },
  unmounted(el) {
    observers.get(el)?.disconnect()
    animations.get(el)?.cancel()
    observers.delete(el)
    animations.delete(el)
  },
}
