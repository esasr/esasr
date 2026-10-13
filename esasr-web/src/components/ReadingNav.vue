<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import MotionIcon from './MotionIcon.vue'
const props = defineProps<{ sections: { id: string; label: string }[] }>()
const { locale } = useI18n()
const active = ref(props.sections[0]?.id || '')
const progress = ref(0)
let frame = 0
let resize: ResizeObserver | undefined
function update() {
  frame = 0
  const header = document.querySelector('.reading-nav')?.getBoundingClientRect().bottom || 120
  let current = props.sections[0]?.id || ''
  for (const section of props.sections) {
    const el = document.getElementById(section.id)
    if (el && el.getBoundingClientRect().top <= header + 32) current = section.id
  }
  active.value = current
  const max = document.documentElement.scrollHeight - window.innerHeight
  progress.value = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0
}
function schedule() { if (!frame) frame = requestAnimationFrame(update) }
function jump(id?: string) {
  const behavior = matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
  if (!id) window.scrollTo({ top: 0, behavior })
  else {
    const target = document.getElementById(id)
    target?.scrollIntoView({ behavior, block: 'start' })
    target?.focus({ preventScroll: true })
  }
}
onMounted(() => {
  window.addEventListener('scroll', schedule, { passive: true })
  window.addEventListener('resize', schedule)
  resize = new ResizeObserver(schedule)
  resize.observe(document.body)
  update()
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', schedule)
  window.removeEventListener('resize', schedule)
  resize?.disconnect()
  cancelAnimationFrame(frame)
})
</script>

<template>
  <nav class="reading-nav" :aria-label="locale === 'en' ? 'On this page' : '页内导航'">
    <div class="reading-links">
      <a v-for="section in sections" :key="section.id" :href="`#${section.id}`"
        :aria-current="active === section.id ? 'location' : undefined" @click.prevent="jump(section.id)">{{ section.label }}</a>
    </div>
    <button class="reading-top" @click="jump()" :aria-label="locale === 'en' ? 'Back to top' : '返回顶部'">
      <MotionIcon name="up" /><span>{{ locale === 'en' ? 'Top' : '顶部' }}</span>
    </button>
    <span class="reading-progress" :style="{ transform: `scaleX(${progress})` }" aria-hidden="true" />
  </nav>
</template>

<style scoped>
.reading-nav { position: sticky; top: var(--header-height); z-index: 15; display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 54px; margin-bottom: 24px; padding: 6px 12px; background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: 12px; box-shadow: var(--shadow-soft); }
.reading-links { display: flex; gap: 4px; overflow-x: auto; min-width: 0; }
a, button { display: inline-flex; align-items: center; gap: 6px; min-height: 38px; padding: 8px 12px; border: 0; border-radius: 8px; color: var(--text-secondary); font: inherit; font-size: 13px; white-space: nowrap; background: transparent; cursor: pointer; }
a[aria-current], a:hover, button:hover { color: var(--primary-color); background: var(--surface-tint); }
.reading-top { flex: none; }
.reading-progress { position: absolute; bottom: 0; left: 12px; right: 12px; height: 2px; background: var(--primary-color); transform-origin: left; pointer-events: none; }
@media (max-width: 600px) { a, button { padding-inline: 9px; } .reading-top span { display: none; } }
</style>
