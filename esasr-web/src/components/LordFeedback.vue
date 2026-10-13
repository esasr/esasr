<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { usePreferredReducedMotion } from '@vueuse/core'
import MotionIcon from './MotionIcon.vue'
withDefaults(defineProps<{ active?: boolean; size?: number }>(), { active: false, size: 48 })
const enabled = ref(false)
const ready = ref(false)
const reduced = usePreferredReducedMotion()
const src = `${import.meta.env.BASE_URL}icons/lordicon/puzzle.json`
let disposed = false
onMounted(async () => {
  try {
    const { defineElement } = await import('@lordicon/element')
    if (disposed) return
    if (!customElements.get('lord-icon')) defineElement()
    enabled.value = true
  } catch { /* Decorative animation must never block search or reading. */ }
})
onBeforeUnmount(() => { disposed = true })
</script>

<template>
  <span class="lord-feedback" :style="{ width: `${size}px`, height: `${size}px` }" aria-hidden="true">
    <MotionIcon v-if="!ready || reduced === 'reduce'" name="search" :size="Math.round(size * .6)" />
    <lord-icon v-if="enabled && reduced !== 'reduce'" :src="src" :trigger="active ? 'loop(1200)' : 'hover'"
      current-color :style="{ opacity: ready ? 1 : 0 }" @ready="ready = true" @error="ready = false" />
  </span>
</template>

<style scoped>
.lord-feedback { position: relative; display: inline-flex; flex: none; align-items: center; justify-content: center; color: var(--primary-color); }
lord-icon { position: absolute; inset: 0; display: block; width: 100%; height: 100%; --lord-icon-primary: var(--primary-color); --lord-icon-secondary: var(--primary-light); }
</style>
