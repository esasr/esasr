import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus, { ElSelect } from 'element-plus'
import axios from 'axios'
import SearchResultsView from '../src/views/SearchResultsView.vue'
import { useSearchStore } from '../src/stores/search'
import i18n from '../src/locales'

vi.mock('axios')
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); sessionStorage.clear() })

describe('results reading workflow', () => {
  it('toggles the responsive filter panel and preserves position before opening a paper', async () => {
    // Node 25 exposes an incomplete native localStorage unless a file is configured.
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: vi.fn(), removeItem: vi.fn() })
    vi.spyOn(axios, 'get').mockResolvedValue({ data: { providers: [{ id: 'test', label: 'Test', models: ['mock'] }] } })
    vi.spyOn(axios, 'post').mockResolvedValue({ data: {
      papers: [{ id: 'ui-paper', title: 'UI paper with a long title', venue: 'Long Venue', authors: 'Test Author', year: 2024, citationCount: 0, relevanceScore: .8 }],
      plan: { intentions: [], decomposed_queries: [] }, trace: [],
    } })
    vi.spyOn(window, 'matchMedia').mockImplementation(query => ({ matches: true, media: query, addEventListener() {}, removeEventListener() {} }) as unknown as MediaQueryList)
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { name: 'search-results', path: '/search', component: SearchResultsView },
      { name: 'paper-detail', path: '/paper/:id', component: { template: '<div>Detail</div>' } },
    ] })
    await router.push('/search?q=layout-test')
    const pinia = createPinia()
    const wrapper = mount(SearchResultsView, { global: {
      plugins: [pinia, router, i18n, ElementPlus], stubs: { MotionIcon: true, LordFeedback: true },
    } })
    await flushPromises()
    await flushPromises()
    expect(wrapper.get('.top-search-input').classes()).toContain('el-input--large')
    expect(wrapper.findComponent(ElSelect).props('size')).toBe('large')
    expect(wrapper.get('.search-header > .el-button').classes()).toContain('el-button--large')
    expect(wrapper.get('.filter-toggle').attributes('aria-expanded')).toBe('false')
    await wrapper.get('.filter-toggle').trigger('click')
    expect(wrapper.get('#search-filters').classes()).toContain('is-open')
    await wrapper.get('.filter-toggle').trigger('click')
    expect(wrapper.get('#search-filters').classes()).not.toContain('is-open')

    Object.defineProperty(window, 'scrollY', { configurable: true, value: 640 })
    await wrapper.get('.paper-title a').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('paper-detail')
    expect(useSearchStore(pinia).get('layout-test', 'test::mock::breadth-3')?.viewState?.scrollY).toBe(640)
    expect(axios.post).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
