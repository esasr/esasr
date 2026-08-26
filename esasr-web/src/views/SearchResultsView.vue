<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { StarFilled, Filter } from '@element-plus/icons-vue'
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { useSearchStore, type SearchViewState } from '@/stores/search'
import { API_BASE } from '@/services/api'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()
const searchStore = useSearchStore()
const query = ref(route.query.q as string || '')
const loading = ref(true)
const searchError = ref('')
const restoredFromCache = ref(false)
const providersLoading = ref(true)
const selectedProvider = ref('')
const llmProviders = ref<{id: string, provider: string, label: string, model: string}[]>([])
const selectedLlm = computed(() =>
  llmProviders.value.find(item => item.id === selectedProvider.value)
)

// LLM Analyzed Data State
const parsedIntentions = ref<{label: string, value: string}[]>([])
const decomposedQueries = ref<string[]>([])
const searchTrace = ref<{stage: string, status: string, detail: string, durationMs: number}[]>([])
const coverage = ref<{
  firstRound: {score: number, gaps: {dimension: string, value: string, hits: number}[]}
  final: {score: number, gaps: {dimension: string, value: string, hits: number}[]}
  secondRoundTriggered: boolean
  secondRoundQueries: string[]
} | null>(null)
const searchMetrics = ref<{
  apiCalls: number
  llmTokens: number
  llmPromptTokens: number
  llmCompletionTokens: number
  llmReasoningTokens: number
  plannerMode: 'cache' | 'heuristic' | 'coalesced' | 'llm' | 'fallback'
  plannerCacheHit: boolean
  plannerCoalesced: boolean
  rawCandidates: number
  returnedPapers: number
  totalDurationMs: number
  sourceCounts: Record<string, number>
  failures: string[]
} | null>(null)

// Real Papers Data from S2
const papers = ref<any[]>([])

// Filtering & Sorting State
const availableVenues = computed(() => {
  const venueCounts = new Map<string, { label: string, count: number }>()
  for (const paper of papers.value) {
    const label = String(paper.venue || '').trim()
    if (!label) continue
    const key = label.toLocaleLowerCase()
    const existing = venueCounts.get(key)
    if (existing) {
      existing.count += 1
    } else {
      venueCounts.set(key, { label, count: 1 })
    }
  }
  return [...venueCounts.values()]
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
    .map(item => item.label)
})
const selectedVenues = ref<string[]>([])
const yearFrom = ref<number | undefined>()
const citationMinimum = ref<number | undefined>()
const openAccessOnly = ref(false)

const sortBy = ref<'relevance' | 'date'>('relevance')
const sortOrder = ref<'desc' | 'asc'>('desc')

const filteredAndSortedPapers = computed(() => {
  // 1. Filter
  let result = papers.value
  if (selectedVenues.value.length > 0) {
    result = result.filter(p => {
      // Simple text matching since Semantic Scholar venues can be messy
      return selectedVenues.value.some(v => p.venue && p.venue.toLowerCase().includes(v.toLowerCase()))
    })
  }
  if (yearFrom.value) result = result.filter(p => (p.year || 0) >= yearFrom.value!)
  if (citationMinimum.value) result = result.filter(p => (p.citationCount || 0) >= citationMinimum.value!)
  if (openAccessOnly.value) result = result.filter(p => p.isOpenAccess)
  
  // 2. Sort
  result = [...result].sort((a, b) => {
    let valA, valB
    if (sortBy.value === 'relevance') {
      valA = a.relevanceScore || 0
      valB = b.relevanceScore || 0
    } else {
      valA = a.year || 0
      valB = b.year || 0
    }
    
    if (valA < valB) return sortOrder.value === 'desc' ? 1 : -1
    if (valA > valB) return sortOrder.value === 'desc' ? -1 : 1
    return 0
  })
  
  return result
})

function applySearchResponse(data: Record<string, any>) {
  parsedIntentions.value = data.plan?.intentions || []
  decomposedQueries.value = data.plan?.decomposed_queries || []
  papers.value = data.papers || []
  searchTrace.value = data.trace || []
  searchMetrics.value = data.metrics || null
  coverage.value = data.coverage || null
}

function currentViewState(): SearchViewState {
  return {
    selectedVenues: [...selectedVenues.value],
    yearFrom: yearFrom.value ?? null,
    citationMinimum: citationMinimum.value ?? null,
    openAccessOnly: openAccessOnly.value,
    sortBy: sortBy.value,
    sortOrder: sortOrder.value,
    scrollY: window.scrollY,
  }
}

function restoreViewState(state?: SearchViewState) {
  if (!state) return
  selectedVenues.value = [...state.selectedVenues]
  yearFrom.value = state.yearFrom ?? undefined
  citationMinimum.value = state.citationMinimum ?? undefined
  openAccessOnly.value = state.openAccessOnly
  sortBy.value = state.sortBy
  sortOrder.value = state.sortOrder
}

function resetViewState() {
  selectedVenues.value = []
  yearFrom.value = undefined
  citationMinimum.value = undefined
  openAccessOnly.value = false
  sortBy.value = 'relevance'
  sortOrder.value = 'desc'
}

const handleSearch = async (forceRefresh = false) => {
  if (!query.value) {
    loading.value = false
    return
  }

  const normalizedQuery = query.value.trim()
  if (!selectedLlm.value) {
    searchError.value = '请选择一个已配置的大模型。'
    loading.value = false
    return
  }
  if (!forceRefresh) {
    const cached = searchStore.get(normalizedQuery, selectedProvider.value)
    if (cached) {
      applySearchResponse(cached.response)
      restoreViewState(cached.viewState)
      restoredFromCache.value = true
      searchError.value = ''
      loading.value = false
      await nextTick()
      window.scrollTo({ top: cached.viewState?.scrollY || 0 })
      return
    }
  }

  loading.value = true
  restoredFromCache.value = false
  searchError.value = ''
  searchTrace.value = []
  searchMetrics.value = null
  coverage.value = null
  resetViewState()

  try {
    const { data } = await axios.post(`${API_BASE}/api/search/run`, {
      query: normalizedQuery,
      limit: 20,
      max_queries: 4,
      results_per_source: 15,
      max_api_calls: 8,
      enable_citation_expansion: false,
      llm_provider: selectedLlm.value.provider,
      llm_model: selectedLlm.value.model,
    })
    applySearchResponse(data)
    searchStore.set(normalizedQuery, selectedProvider.value, data)
    if (route.query.q !== normalizedQuery || route.query.llm !== selectedProvider.value) {
      await router.replace({
        name: 'search-results',
        query: { q: normalizedQuery, llm: selectedProvider.value },
      })
    }

    // Record search history for logged-in users (fire-and-forget)
    if (authStore.isLoggedIn) {
      axios.post(`${API_BASE}/api/user/search-history`, { query: normalizedQuery }).catch(() => {})
    }
  } catch (error) {
    console.error("Failed to perform search:", error)
    searchError.value = '检索流程执行失败。请确认后端服务及学术数据源配置可用。'
  } finally {
    loading.value = false
  }
}

async function loadProviders() {
  providersLoading.value = true
  try {
    const { data } = await axios.get(`${API_BASE}/api/search/providers`)
    llmProviders.value = (data.providers || []).flatMap(
      (provider: {id: string, label: string, models: string[]}) =>
        (provider.models || []).map(model => ({
          id: `${provider.id}::${model}`,
          provider: provider.id,
          label: provider.label,
          model,
        }))
    )
    const requested = typeof route.query.llm === 'string' ? route.query.llm : ''
    const defaultId = data.default
      ? `${data.default.provider}::${data.default.model}`
      : ''
    selectedProvider.value = llmProviders.value.some(item => item.id === requested)
      ? requested
      : (defaultId || llmProviders.value[0]?.id || '')
    if (!selectedProvider.value) {
      searchError.value = '尚未配置可用的大模型 API Key，请先在 .env 中完成配置。'
    }
  } catch (error) {
    console.error('Failed to load LLM providers:', error)
    searchError.value = '无法读取大模型配置，请确认后端服务正常运行。'
  } finally {
    providersLoading.value = false
  }
}

onMounted(async () => {
  await loadProviders()
  if (selectedProvider.value) await handleSearch(false)
  else loading.value = false
})

const viewPaperDetail = (id: string) => {
  searchStore.saveViewState(query.value, selectedProvider.value, currentViewState())
  router.push(`/paper/${id}`)
}

onBeforeUnmount(() => {
  searchStore.saveViewState(query.value, selectedProvider.value, currentViewState())
})

function bibtexValue(value: unknown) {
  return String(value ?? '')
    .replace(/\\/g, '\\\\')
    .replace(/([{}])/g, '\\$1')
    .replace(/\s+/g, ' ')
    .trim()
}

function paperUrl(p: any) {
  const doi = String(p.doi || '').replace(/^https?:\/\/(dx\.)?doi\.org\//i, '')
  if (doi) return `https://doi.org/${doi}`
  if (p.url) return String(p.url)
  if (String(p.id || '').startsWith('s2_')) {
    return `https://www.semanticscholar.org/paper/${encodeURIComponent(p.sourceId || String(p.id).slice(3))}`
  }
  if (p.id && !p.offline) return `https://openalex.org/${encodeURIComponent(p.id)}`
  return ''
}

function exportResults(format: 'bibtex' | 'markdown') {
  const rows = filteredAndSortedPapers.value
  const text = format === 'bibtex'
    ? rows.map((p, index) => {
        const fields = [
          `  title={${bibtexValue(p.title)}}`,
          `  author={${bibtexValue(p.authors)}}`,
          `  journal={${bibtexValue(p.venue)}}`,
          `  year={${bibtexValue(p.year)}}`,
        ]
        const url = paperUrl(p)
        if (url) fields.push(`  url={${bibtexValue(url)}}`)
        return `@article{paper${index + 1},\n${fields.join(',\n')}\n}`
      }).join('\n\n')
    : rows.map(p => {
        const url = paperUrl(p)
        const title = url ? `[${p.title}](${url})` : p.title
        return `- **${title}** (${p.year || 'n.d.'})  \n  ${p.authors} · *${p.venue}* · ${p.citationCount || 0} citations`
      }).join('\n')
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `esasr-results.${format === 'bibtex' ? 'bib' : 'md'}`
  link.click()
  URL.revokeObjectURL(link.href)
}
</script>

<template>
  <div class="search-results-container">
    <div class="search-header">
      <el-input
        v-model="query"
        :placeholder="t('search.placeholder')"
        size="large"
        class="top-search-input"
        @keyup.enter="handleSearch(true)"
      />
      <el-select
        v-model="selectedProvider"
        class="llm-provider-select"
        :loading="providersLoading"
        :disabled="providersLoading || loading || llmProviders.length === 0"
        placeholder="选择大模型"
        aria-label="选择用于查询规划的大模型"
      >
        <el-option
          v-for="provider in llmProviders"
          :key="provider.id"
          :label="`${provider.label} · ${provider.model}`"
          :value="provider.id"
        />
      </el-select>
      <el-button
        type="primary"
        size="large"
        :loading="loading"
        :disabled="!selectedProvider"
        @click="handleSearch(true)"
      >
        {{ t('search.searchBtn') }}
      </el-button>
    </div>

    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="5" animated />
    </div>

    <el-alert v-else-if="searchError" :title="searchError" type="error" :closable="false" show-icon class="search-error" />

    <div v-else class="results-content">
      <section v-if="searchMetrics" class="pipeline-overview" aria-label="本次检索过程">
        <el-tag v-if="restoredFromCache" class="cache-badge" type="success" effect="plain">
          已从缓存恢复 · 未消耗 Token
        </el-tag>
        <el-tag
          v-else-if="searchMetrics.plannerMode !== 'llm'"
          class="cache-badge"
          type="success"
          effect="plain"
        >
          {{ searchMetrics.plannerMode === 'cache' ? '共享规划缓存' : searchMetrics.plannerMode === 'heuristic' ? '本地规则规划' : searchMetrics.plannerMode === 'coalesced' ? '合并重复规划' : '规划降级' }} · 未消耗 Token
        </el-tag>
        <div class="pipeline-metrics">
          <div><strong>{{ searchMetrics.rawCandidates }}</strong><span>原始候选</span></div>
          <div><strong>{{ searchMetrics.returnedPapers }}</strong><span>融合结果</span></div>
          <div><strong>{{ searchMetrics.apiCalls }}</strong><span>API 调用</span></div>
          <div><strong>{{ searchMetrics.llmTokens }}</strong><span>规划 Token</span></div>
          <div><strong>{{ (searchMetrics.totalDurationMs / 1000).toFixed(1) }}s</strong><span>端到端耗时</span></div>
        </div>
        <div class="pipeline-trace">
          <div v-for="(step, index) in searchTrace" :key="step.stage" class="trace-step">
            <span class="trace-index">{{ index + 1 }}</span>
            <div><strong>{{ step.stage }}</strong><small>{{ step.detail }} · {{ step.durationMs }}ms</small></div>
          </div>
        </div>
        <el-alert
          v-if="searchMetrics.failures?.length"
          :title="`部分数据源降级：${searchMetrics.failures.join('；')}`"
          type="warning"
          :closable="false"
          show-icon
        />
      </section>

      <el-row :gutter="24">
        <el-col :span="6">
          <!-- Sidebar: Filters & Analysis -->
          <div class="analysis-sidebar">
            <el-card class="analysis-card" shadow="never">
              <template #header>
                <div class="card-header">
                  <el-icon><Filter /></el-icon>
                  <span style="margin-left: 8px">{{ t('search.filters') }}</span>
                </div>
              </template>
              <div v-if="availableVenues.length" class="filter-section">
                <div class="filter-title">{{ t('search.venues') }}</div>
                <el-checkbox-group v-model="selectedVenues" class="venue-checkboxes">
                  <el-checkbox v-for="venue in availableVenues" :key="venue" :label="venue" :value="venue">
                    {{ venue }}
                  </el-checkbox>
                </el-checkbox-group>
              </div>
              <div class="filter-section advanced-filters">
                <div class="filter-title">高级条件</div>
                <el-input-number v-model="yearFrom" :min="1900" :max="new Date().getFullYear()" placeholder="最早年份" controls-position="right" />
                <el-input-number v-model="citationMinimum" :min="0" placeholder="最低引用" controls-position="right" />
                <el-checkbox v-model="openAccessOnly">仅开放获取</el-checkbox>
              </div>
            </el-card>

            <el-card class="analysis-card mt-4" shadow="never">
              <template #header>
                <div class="card-header">
                  <span>{{ t('search.queryIntentions') }}</span>
                </div>
              </template>
              <div class="intentions-list">
                <div v-for="item in parsedIntentions" :key="item.label" class="intention-item">
                  <span class="intention-label">{{ item.label }}:</span>
                  <el-tag size="small" type="primary">{{ item.value }}</el-tag>
                </div>
              </div>
            </el-card>

            <el-card class="analysis-card mt-4" shadow="never">
              <template #header>
                <div class="card-header">
                  <span>{{ t('search.decomposedQueries') }}</span>
                </div>
              </template>
              <div class="decomposed-list">
                <el-tag 
                  v-for="(subq, index) in decomposedQueries" 
                  :key="index"
                  class="subq-tag"
                  type="info"
                  effect="plain"
                >
                  {{ subq }}
                </el-tag>
              </div>
            </el-card>

            <el-card v-if="coverage" class="analysis-card mt-4" shadow="never">
              <template #header>
                <div class="card-header">
                  <span>约束覆盖诊断</span>
                  <el-tag v-if="coverage.secondRoundTriggered" size="small" type="warning">已补检</el-tag>
                </div>
              </template>
              <el-progress
                :percentage="Math.round(coverage.final.score * 100)"
                :status="coverage.final.score >= 0.8 ? 'success' : 'warning'"
              />
              <p class="coverage-change">
                首轮 {{ Math.round(coverage.firstRound.score * 100) }}%
                → 最终 {{ Math.round(coverage.final.score * 100) }}%
              </p>
              <div v-if="coverage.final.gaps.length" class="coverage-gaps">
                <span>仍未充分覆盖</span>
                <el-tag v-for="gap in coverage.final.gaps" :key="`${gap.dimension}-${gap.value}`" size="small" type="danger" effect="plain">
                  {{ gap.value }}
                </el-tag>
              </div>
            </el-card>
          </div>
        </el-col>
        
        <el-col :span="18">
          <!-- Main Results List -->
          <div class="results-list">
              <div class="results-toolbar">
              <div class="results-summary">
                {{ t('search.found') }} <strong>{{ filteredAndSortedPapers.length }}</strong> {{ t('search.papers') }}
              </div>
              
                <div class="sort-controls">
                <span class="sort-label">{{ t('search.sortBy') }}</span>
                <el-radio-group v-model="sortBy" size="small" class="sort-group">
                  <el-radio-button value="relevance">{{ t('search.relevance') }}</el-radio-button>
                  <el-radio-button value="date">{{ t('search.publishDate') }}</el-radio-button>
                </el-radio-group>
                
                <el-radio-group v-model="sortOrder" size="small">
                  <el-radio-button value="desc">{{ t('search.orderDesc') }}</el-radio-button>
                  <el-radio-button value="asc">{{ t('search.orderAsc') }}</el-radio-button>
                </el-radio-group>
                </div>
                <el-dropdown @command="exportResults">
                  <el-button size="small">导出结果</el-button>
                  <template #dropdown><el-dropdown-menu><el-dropdown-item command="bibtex">BibTeX (.bib)</el-dropdown-item><el-dropdown-item command="markdown">Markdown (.md)</el-dropdown-item></el-dropdown-menu></template>
                </el-dropdown>
            </div>
            
            <el-card 
              v-for="paper in filteredAndSortedPapers" 
              :key="paper.id" 
              class="paper-card" 
              shadow="hover"
              @click="viewPaperDetail(paper.id)"
            >
              <h3 class="paper-title">{{ paper.title }}</h3>
              <div class="paper-meta">
                <span class="authors">{{ paper.authors }}</span>
                <el-divider direction="vertical" />
                <span class="venue">{{ paper.venue }}</span>
                <el-divider direction="vertical" />
                <span class="year">{{ paper.year }}</span>
                <el-divider direction="vertical" />
                <span class="citations">{{ t('search.citations') }}: {{ paper.citationCount }}</span>
                <el-tag v-if="paper.isOpenAccess" size="small" type="success" effect="plain">Open Access</el-tag>
                <el-tag size="small" :type="paper.relevanceLevel === '高度相关' ? 'primary' : 'info'" effect="dark">
                  {{ paper.relevanceLevel || '相关论文' }}
                </el-tag>
                <el-tag v-if="paper.crossEncoderScore !== undefined" size="small" type="warning" effect="plain">
                  CE {{ Number(paper.crossEncoderScore).toFixed(3) }}
                </el-tag>
              </div>
              <p class="paper-abstract">{{ paper.abstract }}</p>
              
              <div class="recommend-reason">
                <el-icon color="#e6a23c"><StarFilled /></el-icon>
                <div>
                  <span><strong>{{ t('search.recommendReason') }}</strong> {{ paper.recommendReason }}</span>
                  <div v-if="paper.sources?.length" class="evidence-row">
                    <el-tag v-for="source in paper.sources" :key="source" size="small" type="info" effect="plain">{{ source }}</el-tag>
                    <el-tag v-for="term in paper.matchedTerms || []" :key="term" size="small" effect="plain">{{ term }}</el-tag>
                  </div>
                  <details
                    v-if="paper.criterionEvidence?.length"
                    class="criterion-evidence"
                    @click.stop
                  >
                    <summary>
                      {{ t('search.evidence') }} · {{ Math.round((paper.evidenceCoverage || 0) * 100) }}%
                    </summary>
                    <div
                      v-for="(item, index) in paper.criterionEvidence"
                      :key="`${item.criterion}-${item.value}-${index}`"
                      class="evidence-item"
                    >
                      <div class="evidence-heading">
                        <el-tag size="small" type="primary" effect="plain">{{ item.criterion }}</el-tag>
                        <strong>{{ item.value }}</strong>
                        <span>{{ item.source === 'full_text' ? t('search.fullTextEvidence') : t('search.abstractEvidence') }}</span>
                      </div>
                      <p>{{ item.snippet }}</p>
                    </div>
                  </details>
                </div>
              </div>
            </el-card>
            
            <el-empty v-if="filteredAndSortedPapers.length === 0" description="No papers match the selected filters" />
          </div>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<style scoped lang="scss">
.search-results-container {
  max-width: 1200px;
  margin: 0 auto;
}

.search-header {
  margin-bottom: 32px;
  max-width: 1040px;
  display: flex;
  gap: 10px;
}
.search-error { max-width: 800px; }
.pipeline-overview {
  position: relative;
  margin-bottom: 24px;
  padding: 18px 20px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-surface);
}
.cache-badge { position: absolute; top: 14px; right: 16px; }
.pipeline-metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}
.pipeline-metrics > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px;
  border-radius: 8px;
  background: rgba(63, 81, 181, .06);
}
.pipeline-metrics strong { color: var(--primary-color); font-size: 22px; }
.pipeline-metrics span { color: var(--text-secondary); font-size: 12px; }
.pipeline-trace { display: flex; gap: 16px; margin-bottom: 14px; }
.trace-step { display: flex; min-width: 0; flex: 1; align-items: center; gap: 9px; }
.trace-index {
  display: grid;
  width: 26px;
  height: 26px;
  flex: 0 0 26px;
  place-items: center;
  border-radius: 50%;
  background: var(--primary-color);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}
.trace-step div { display: flex; min-width: 0; flex-direction: column; }
.trace-step strong { color: var(--text-primary); font-size: 13px; }
.trace-step small {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-search-input {
  flex: 1;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}
.llm-provider-select { width: 240px; flex: 0 0 240px; }

.analysis-card {
  border-radius: 8px;
  background-color: var(--bg-surface);
  
  .card-header {
    font-weight: 600;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
}
.coverage-change { margin: 10px 0 0; color: var(--text-secondary); font-size: 12px; }
.coverage-gaps { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.coverage-gaps > span { width: 100%; color: var(--text-secondary); font-size: 12px; }

.mt-4 {
  margin-top: 16px;
}

.filter-section {
  .filter-title {
    font-size: 14px;
    font-weight: 500;
    margin-bottom: 8px;
    color: var(--text-primary);
  }
}

.venue-checkboxes {
  display: flex;
  flex-direction: column;
}
.advanced-filters { display: flex; flex-direction: column; gap: 10px; margin-top: 18px; }

.intention-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
  
  .intention-label {
    color: var(--text-secondary);
  }
}

.decomposed-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.subq-tag {
  white-space: normal;
  height: auto;
  text-align: left;
  line-height: 1.4;
  padding: 6px 8px;
}

.results-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.results-summary {
  color: var(--text-secondary);
  font-size: 14px;
}

.sort-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sort-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.sort-group {
  margin-right: 8px;
}

.paper-card {
  margin-bottom: 16px;
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.2s ease;
  background-color: var(--bg-surface);
  
  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  }
}

.paper-title {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: var(--primary-color);
  line-height: 1.4;
}

.paper-meta {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
  
  .venue {
    font-weight: 500;
    color: #008080;
  }
}

.paper-abstract {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  margin-bottom: 16px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.recommend-reason {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  background-color: rgba(230, 162, 60, 0.1);
  padding: 12px;
  border-radius: 6px;
  font-size: 13px;
  color: #e6a23c;

  strong {
    color: #b88230;
  }
}
.evidence-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.criterion-evidence {
  margin-top: 10px;
  color: var(--text-primary);

  summary {
    cursor: pointer;
    color: var(--el-color-primary);
    font-weight: 600;
  }
}
.evidence-item {
  margin-top: 8px;
  padding: 9px 10px;
  border-left: 3px solid var(--el-color-primary-light-5);
  border-radius: 4px;
  background: var(--el-fill-color-lighter);

  p { margin: 6px 0 0; line-height: 1.55; color: var(--text-secondary); }
}
.evidence-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;

  span { color: var(--text-secondary); font-size: 12px; }
}

@media (max-width: 900px) {
  .search-header { flex-wrap: wrap; }
  .top-search-input { min-width: 100%; }
  .llm-provider-select { width: auto; flex: 1; }
  .pipeline-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .pipeline-trace { flex-direction: column; }
  .results-toolbar { align-items: flex-start; flex-direction: column; gap: 12px; }
  .sort-controls { flex-wrap: wrap; }
}
</style>
