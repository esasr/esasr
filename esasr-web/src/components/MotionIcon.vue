<script setup lang="ts">
import { computed } from 'vue'
import { MorphIcon } from 'morphicons/vue'

// Shared 24-unit stroke grid. Optical offsets never change the layout box.
const paths = {
  filter: 'M4 6h16 M7 12h10 M10 18h4',
  close: 'M6 6l12 12 M18 6L6 18',
  bookmark: 'M6 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16l-6-4z',
  check: 'M5 12l4 4L19 6',
  up: 'M5 15l7-7 7 7',
  document: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M8 13h8 M8 17h6',
  graph: 'M12 7v5 M5 12h14 M5 12v5 M19 12v5 M9 3h6v4H9z M2 17h6v4H2z M16 17h6v4h-6z',
  light: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v2 M12 20v2 M2 12h2 M20 12h2 M5 5l1 1 M18 18l1 1 M5 19l1-1 M18 6l1-1',
  dark: 'M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13z',
  auto: 'M4 3h16v14H4z M8 21h8 M12 17v4',
  search: 'M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16 M17 17l4 4',
} as const
const props = withDefaults(defineProps<{ name: keyof typeof paths; size?: number }>(), { size: 18 })
const path = computed(() => paths[props.name])
</script>

<template>
  <span class="motion-icon" :style="{ '--icon-size': `${size}px` }" aria-hidden="true">
    <MorphIcon :icon="path" :size="size" :stroke-width="1.8" reduced-motion="user" spring="snappy" />
  </span>
</template>

<style scoped>
.motion-icon { display: inline-flex; align-items: center; justify-content: center; width: var(--icon-size); height: var(--icon-size); flex: 0 0 var(--icon-size); vertical-align: middle; }
.motion-icon :deep(svg) { display: block; width: var(--icon-size); height: var(--icon-size); transform: translateY(var(--icon-optical-y, -.5px)); }
</style>
