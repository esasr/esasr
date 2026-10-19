<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Handle, MarkerType, Position, VueFlow, useVueFlow } from '@vue-flow/core'
import { useFullscreen, usePreferredReducedMotion } from '@vueuse/core'
import { FileText, Maximize, Minimize, Scan, Plus, Minus, ExternalLink } from 'lucide-vue-next'
import axios from 'axios'
import { API_BASE } from '@/services/api'
import LordFeedback from './LordFeedback.vue'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

const props = defineProps<{ paperId: string; paper: Record<string, any>; relatedPapers: Record<string, any>[] }>()
const emit = defineEmits<{ openPaper: [id: string] }>()
const root = ref<HTMLElement>()
const { toggle, isFullscreen, isSupported } = useFullscreen(root)
const { fitView, zoomIn, zoomOut } = useVueFlow()
const reduced = usePreferredReducedMotion()
const raw = ref<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] })
const loading = ref(false)
const error = ref('')
const filter = ref('all')
const selected = ref('')
let request: AbortController | undefined
const labels: Record<string, string> = { current: '当前论文', reference: '参考文献', citing: '引用本文', related: '相关研究' }
const colors: Record<string, string> = { current: '#5865c9', reference: '#218879', citing: '#397fbd', related: '#a37735' }
const records = computed(() => {
  const known = new Map(props.relatedPapers.map(p => [p.id, p]))
  known.set(props.paperId, props.paper)
  return raw.value.nodes.map(n => {
    const relations = raw.value.edges.filter(e => e.source === n.id || e.target === n.id)
    const group = n.id === props.paperId ? 'current' : relations.some(e => e.type === 'CITES' && e.source === props.paperId && e.target === n.id) ? 'reference' : relations.some(e => e.type === 'CITES' && e.target === props.paperId && e.source === n.id) ? 'citing' : 'related'
    const info = { ...n.data, ...known.get(n.id) }
    const label = info.title || n.style?.labelText || ''
    const placeholder = !label || /^(Reference|Related) \d+$/.test(label)
    return { id: String(n.id), group, title: placeholder ? '题名暂未提供' : label, year: info.year, venue: info.venue, relations }
  }).filter(n => n.group === 'current' || (n.title !== '题名暂未提供' && !/^W\d+$/.test(n.title)))
})
const groups = computed(() => ['reference', 'citing', 'related'].map(id => ({ id, label: labels[id], count: records.value.filter(n => n.group === id).length })))
const visible = computed(() => records.value.filter(n => n.group === 'current' || filter.value === 'all' || n.group === filter.value))
const nodes = computed(() => {
  const counts = { reference: 0, citing: 0, related: 0 }
  const size = Math.max(1, ...groups.value.filter(g => filter.value === 'all' || filter.value === g.id).map(g => g.count))
  return visible.value.map(n => {
    const index = n.group === 'current' ? 0 : counts[n.group as keyof typeof counts]++
    const x = n.group === 'reference' ? 0 : n.group === 'citing' ? 720 : n.group === 'related' ? (groups.value.some(g => g.id === 'citing' && g.count > 0) ? 1080 : 720) : 360
    const y = n.group === 'current' ? (size - 1) * 85 : index * 170
    return { id: n.id, type: 'paper', position: { x, y }, data: n, selectable: false, draggable: false }
  })
})
const edges = computed(() => {
  const ids = new Set(visible.value.map(n => n.id))
  const positions = new Map(nodes.value.map(n => [n.id, n.position]))
  return raw.value.edges.filter(e => ids.has(e.source) && ids.has(e.target)).map((e, i) => {
    const semantic = e.type === 'RELATED'
    const source = positions.get(String(e.source))
    const target = positions.get(String(e.target))
    const toRight = (target?.x ?? 0) > (source?.x ?? 0)
    const vertical = source?.x === target?.x
    const toBottom = (target?.y ?? 0) > (source?.y ?? 0)
    return { id: `relation-${i}`, source: e.source, target: e.target, type: 'straight',
      sourceHandle: vertical ? (toBottom ? 'bottom-out' : 'top-out') : (toRight ? 'right-out' : 'left-out'),
      targetHandle: vertical ? (toBottom ? 'top-in' : 'bottom-in') : (toRight ? 'left-in' : 'right-in'),
      markerEnd: semantic ? undefined : { type: MarkerType.ArrowClosed, color: '#8699b1', width: 16, height: 16 },
      style: { stroke: '#8699b1', strokeWidth: 1.5, strokeDasharray: semantic ? '5 5' : undefined, opacity: selected.value && e.source !== selected.value && e.target !== selected.value ? 0.25 : 0.85 },
    }
  })
})
const active = computed(() => records.value.find(n => n.id === selected.value))
function fit() { void nextTick(() => fitView({ padding: 0.15, maxZoom: 1, duration: reduced.value === 'reduce' ? 0 : 250 })) }
async function load() {
  request?.abort()
  const controller = new AbortController(); request = controller
  loading.value = true; error.value = ''; selected.value = ''; raw.value = { nodes: [], edges: [] }
  try {
    const response = await axios.get(`${API_BASE}/api/papers/${encodeURIComponent(props.paperId)}/graph`, { signal: controller.signal })
    if (controller.signal.aborted) return
    const graph = response.data.data
    if (graph?.nodes?.some((n: any) => n.style?.labelText === 'API Error')) throw new Error('source unavailable')
    raw.value = { nodes: graph?.nodes || [], edges: graph?.edges || [] }
  } catch { if (!controller.signal.aborted) error.value = '关系数据暂时不可用，请稍后重试。' }
  finally { if (!controller.signal.aborted) loading.value = false }
}
watch(() => props.paperId, load, { immediate: true })
watch(filter, () => { selected.value = ''; fit() })
onBeforeUnmount(() => request?.abort())
async function fullscreen() { try { await toggle(); fit() } catch { error.value = '浏览器未允许全屏，可继续在当前窗口查看。' } }
</script>

<template>
  <section ref="root" class="relationship" :class="{ expanded: isFullscreen }" aria-label="论文关系探索">
    <div class="relationship-toolbar">
      <div class="relationship-filters" aria-label="关系类型筛选">
        <button :aria-pressed="filter === 'all'" @click="filter = 'all'">全部 <span>{{ records.length ? records.length - 1 : 0 }}</span></button>
        <button v-for="g in groups" :key="g.id" :aria-pressed="filter === g.id" @click="filter = g.id">{{ g.label }} <span>{{ g.count }}</span></button>
      </div>
      <div class="relationship-tools">
        <button aria-label="放大关系图" title="放大" @click="zoomIn()"><Plus :size="17" /></button>
        <button aria-label="缩小关系图" title="缩小" @click="zoomOut()"><Minus :size="17" /></button>
        <button aria-label="适配全部节点" title="居中适配" @click="fit"><Scan :size="17" /></button>
        <button v-if="isSupported" aria-label="切换关系图全屏" title="全屏" @click="fullscreen"><component :is="isFullscreen ? Minimize : Maximize" :size="17" /></button>
      </div>
    </div>
    <div v-if="loading" class="relationship-state" role="status"><LordFeedback active :size="56" /><p>正在获取论文关系</p></div>
    <div v-else-if="error" class="relationship-state" role="status"><p>{{ error }}</p><button @click="load">重新加载</button></div>
    <div v-else-if="!raw.edges.length" class="relationship-state"><FileText :size="32" /><p>当前来源尚未提供可展示的关系</p><small>不将缺失记录解释为不存在引用。</small></div>
    <div v-else class="relationship-canvas">
      <VueFlow :nodes="nodes" :edges="edges" :min-zoom="0.12" :max-zoom="1.5" :nodes-connectable="false" :nodes-draggable="false" :zoom-on-scroll="false" :prevent-scrolling="false" :delete-key-code="null" :edges-updatable="false" @nodes-initialized="fit" @pane-click="selected = ''">
        <template #node-paper="{ data, id }">
          <Handle id="left-out" type="source" :position="Position.Left" /><Handle id="right-in" type="target" :position="Position.Right" />
          <Handle id="right-out" type="source" :position="Position.Right" /><Handle id="left-in" type="target" :position="Position.Left" />
          <Handle id="bottom-out" type="source" :position="Position.Bottom" /><Handle id="top-in" type="target" :position="Position.Top" />
          <Handle id="top-out" type="source" :position="Position.Top" /><Handle id="bottom-in" type="target" :position="Position.Bottom" />
          <button class="paper-node nodrag" :class="{ active: selected === id, central: data.group === 'current' }" :style="{ '--node-accent': colors[data.group] }" :aria-pressed="selected === id" :title="data.title" @click.stop="selected = id">
            <span class="node-kind"><FileText :size="14" />{{ labels[data.group] }}</span>
            <strong>{{ data.title }}</strong>
            <span class="node-meta">{{ data.year || '年份未提供' }}<span v-if="data.venue"> · {{ data.venue }}</span></span>
          </button>
        </template>
      </VueFlow>
    </div>
    <div v-if="active" class="relationship-preview" aria-live="polite">
      <div><span>{{ labels[active.group] }} · {{ active.id }}</span><h4>{{ active.title }}</h4><p v-if="active.group === 'related'">相关性推荐不代表真实引用关系。</p></div>
      <button v-if="active.id !== paperId" class="open-paper" @click="emit('openPaper', active.id)">查看论文 <ExternalLink :size="15" /></button>
    </div>
    <footer class="relationship-footer"><span>仅展示已取得题名的节点</span><span>实线箭头：引用方 → 被引用方</span><span>虚线：相关研究</span><span>拖动画布 · 双指缩放 · 点击卡片预览</span></footer>
  </section>
</template>

<style scoped>
.relationship { background: var(--bg-surface); color: var(--text-primary); border: 1px solid var(--border-color); border-radius: 14px; overflow: hidden; }
.relationship-toolbar { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 10px; padding: 12px; border-bottom: 1px solid var(--border-color); }
.relationship-filters,.relationship-tools { display: flex; gap: 4px; flex-wrap: wrap; }
.relationship button { cursor: pointer; font: inherit; }
.relationship-toolbar button,.relationship-state button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 34px; border: 1px solid transparent; border-radius: 7px; padding: 6px 9px; background: transparent; color: var(--text-secondary); font-size: 12px; }
.relationship-toolbar button:hover,.relationship-toolbar button[aria-pressed=true] { background: var(--surface-tint); color: var(--primary-color); }
.relationship button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 3px; }
.relationship-filters span { opacity: .7; font-variant-numeric: tabular-nums; }
.relationship-canvas { height: 640px; background-color: var(--bg-color); background-image: radial-gradient(#8794aa35 .8px, transparent .8px); background-size: 18px 18px; }
.paper-node { pointer-events: auto; width: 260px; height: 154px; display: flex; flex-direction: column; gap: 10px; padding: 15px; text-align: left; border: 1px solid var(--border-color); border-top: 3px solid var(--node-accent); border-radius: 11px; background: var(--bg-surface); color: var(--text-primary); box-shadow: 0 4px 14px #24344a0b; transition: box-shadow .18s, border-color .18s; }
.paper-node:hover,.paper-node.active { border-color: var(--node-accent); box-shadow: 0 5px 20px #24344a23; }
.paper-node.central { box-shadow: 0 5px 22px #5865c921; }
.node-kind { display: flex; gap: 6px; align-items: center; color: var(--node-accent); font-size: 11px; font-weight: 600; }
.paper-node strong { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; font-size: 14px; line-height: 1.5; }
.node-meta { margin-top: auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; color: var(--text-secondary); max-width: 100%; }
.relationship :deep(.vue-flow__handle) { opacity: 0; pointer-events: none; }
.relationship-preview { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 16px; border-top: 1px solid var(--border-color); }
.relationship-preview > div { min-width: 0; }.relationship-preview span,.relationship-preview p { color: var(--text-secondary); font-size: 12px; margin: 0; overflow-wrap: anywhere; }.relationship-preview h4 { margin: 7px 0; font-size: 14px; line-height: 1.5; overflow-wrap: anywhere; }
.open-paper { display: flex; align-items: center; gap: 6px; flex-shrink: 0; background: var(--primary-color); color: white; border: 0; border-radius: 7px; padding: 10px 12px; font-size: 12px !important; }
.relationship-footer { display: flex; flex-wrap: wrap; gap: 8px 18px; padding: 12px 16px; border-top: 1px solid var(--border-color); font-size: 11px; color: var(--text-secondary); }
.relationship-state { min-height: 280px; display: flex; align-items: center; justify-content: center; flex-direction: column; color: var(--text-secondary); font-size: 13px; }
.expanded { height: 100dvh; border-radius: 0; display: flex; flex-direction: column; }.expanded .relationship-canvas { flex: 1; min-height: 0; }
@media(max-width: 600px) { .relationship-canvas { height: 450px; }.relationship-preview { align-items: flex-start; flex-direction: column; } }
@media(prefers-reduced-motion: reduce) { .paper-node { transition: none; } }
</style>
