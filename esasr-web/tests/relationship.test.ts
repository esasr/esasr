import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { VueFlow } from '@vue-flow/core'
import PaperRelationshipGraph from '../src/components/PaperRelationshipGraph.vue'

vi.mock('axios', () => ({ default: { get: vi.fn() } }))
vi.mock('@vue-flow/core', () => ({
  VueFlow: { props: ['nodes', 'edges'], template: '<div><template v-for="node in nodes" :key="node.id"><slot name="node-paper" v-bind="node" /></template></div>' },
  Handle: { template: '<span />' }, MarkerType: { ArrowClosed: 'arrowclosed' },
  Position: { Left: 'left', Right: 'right', Top: 'top', Bottom: 'bottom' },
  useVueFlow: () => ({ fitView: vi.fn(), zoomIn: vi.fn(), zoomOut: vi.fn() }),
}))
const graph = { nodes: ['center', 'ref', 'cite', 'related'].map(id => ({ id, style: { labelText: id === 'ref' ? 'A real reference title' : id } })), edges: [
  { source: 'center', target: 'ref', type: 'CITES' },
  { source: 'cite', target: 'center', type: 'CITES' },
  { source: 'center', target: 'related', type: 'RELATED' },
] }
const create = () => mount(PaperRelationshipGraph, { props: { paperId: 'center', paper: { title: 'Current title' }, relatedPapers: [] }, global: { stubs: { LordFeedback: true } } })
beforeEach(() => { vi.mocked(axios.get).mockReset(); vi.mocked(axios.get).mockResolvedValue({ data: { data: graph } }) })
describe('relationship graph', () => {
  it('preserves citation direction and distinguishes related evidence', async () => {
    const w = create(); await flushPromises()
    expect(w.findAll('.paper-node')).toHaveLength(4)
    expect(w.text()).toContain('A real reference title')
    expect(w.text()).not.toContain('题名暂未提供')
    const edges = w.findComponent(VueFlow).props('edges')!
    expect(edges[0]).toMatchObject({ source: 'center', target: 'ref', markerEnd: { type: 'arrowclosed' } })
    expect(edges[2]?.markerEnd).toBeUndefined()
    expect(edges.every((edge: { type: string }) => edge.type === 'straight')).toBe(true)
    expect(edges[0]).toMatchObject({ sourceHandle: 'left-out', targetHandle: 'right-in' })
    expect(edges[2]).toMatchObject({ sourceHandle: 'right-out', targetHandle: 'left-in' })
    const nodes = w.findComponent(VueFlow).props('nodes')!
    expect(nodes.find((n: { id: string }) => n.id === 'related')?.position.x).toBeGreaterThan(nodes.find((n: { id: string }) => n.id === 'cite')?.position.x)
    expect(w.text()).toContain('引用方 → 被引用方')
    await w.findAll('.paper-node')[3]!.trigger('click')
    expect(w.text()).toContain('相关性推荐不代表真实引用关系')
    await w.get('.open-paper').trigger('click')
    expect(w.emitted('openPaper')?.[0]).toEqual(['related'])
    w.unmount()
  })
  it('hides missing titles and their edges without fabricating metadata', async () => {
    const missing = { ...graph, nodes: graph.nodes.map(n => n.id === 'ref' ? { ...n, style: { labelText: 'Reference 1' } } : n) }
    vi.mocked(axios.get).mockResolvedValueOnce({ data: { data: missing } })
    const w = create(); await flushPromises()
    expect(w.findAll('.paper-node')).toHaveLength(3)
    expect(w.text()).not.toContain('题名暂未提供')
    const edges = w.findComponent(VueFlow).props('edges')!
    expect(edges.some((e: { target: string }) => e.target === 'ref')).toBe(false)
    w.unmount()
  })
  it('filters references without navigating away', async () => {
    const w = create(); await flushPromises()
    await w.findAll('.relationship-filters button')[1]!.trigger('click')
    expect(w.findAll('.paper-node')).toHaveLength(2)
    expect(w.emitted('openPaper')).toBeUndefined(); w.unmount()
  })
  it('distinguishes source failure from empty relationships', async () => {
    vi.mocked(axios.get).mockRejectedValueOnce(new Error('offline'))
    const w = create(); await flushPromises()
    expect(w.text()).toContain('关系数据暂时不可用')
    await w.get('.relationship-state button').trigger('click'); await flushPromises()
    expect(w.findAll('.paper-node')).toHaveLength(4); w.unmount()
  })
})
