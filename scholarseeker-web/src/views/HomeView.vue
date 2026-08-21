<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { API_BASE } from '@/services/api'

const router = useRouter()
const { tm, t } = useI18n()
const searchQuery = ref('')
const recommendations = ref<any[]>([])
const recommendationsLoading = ref(false)
const authStore = useAuthStore()
const providersLoading = ref(true)
const selectedProvider = ref('')
const llmProviders = ref<{id: string, provider: string, label: string, model: string}[]>([])
const providerError = ref('')

const handleSearch = () => {
  if (!searchQuery.value.trim() || !selectedProvider.value) return
  router.push({
    name: 'search-results',
    query: { q: searchQuery.value, llm: selectedProvider.value }
  })
}

const selectExample = (query: string) => {
  searchQuery.value = query
  handleSearch()
}

const defaultSuggestions = computed(() => tm('home.examples') as string[])
const suggestedQueries = ref<string[]>([])

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
    selectedProvider.value = data.default
      ? `${data.default.provider}::${data.default.model}`
      : (llmProviders.value[0]?.id || '')
    if (!selectedProvider.value) {
      providerError.value = '尚未配置可用的大模型 API Key'
    }
  } catch (error) {
    console.error('Failed to load LLM providers', error)
    providerError.value = '无法读取大模型配置'
  } finally {
    providersLoading.value = false
  }
}

onMounted(async () => {
  await loadProviders()
  if (!authStore.isLoggedIn) {
    suggestedQueries.value = defaultSuggestions.value
    return
  }
  recommendationsLoading.value = true
  try {
    const [papers, queries] = await Promise.all([
      axios.get(`${API_BASE}/api/user/recommendations`),
      axios.get(`${API_BASE}/api/user/recommended-queries`),
    ])
    recommendations.value = papers.data.data || []
    suggestedQueries.value = queries.data.data?.length ? queries.data.data : defaultSuggestions.value
  } catch (error) {
    console.error('Failed to load intelligent recommendations', error)
    suggestedQueries.value = defaultSuggestions.value
  } finally {
    recommendationsLoading.value = false
  }
})

function openPaper(id: string) {
  router.push({ name: 'paper-detail', params: { id } })
}
</script>

<template>
  <div class="home-container">
    <div class="search-section">
      <h1 class="title">Scholar<span class="highlight">Seeker</span></h1>
      <p class="subtitle">{{ t('home.subtitle') }}</p>
      
      <div class="search-box">
        <el-input
          v-model="searchQuery"
          :placeholder="t('home.searchPlaceholder')"
          size="large"
          class="search-input"
          @keyup.enter="handleSearch"
        />
        <el-select
          v-model="selectedProvider"
          class="llm-provider-select"
          size="large"
          :loading="providersLoading"
          :disabled="providersLoading || llmProviders.length === 0"
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
          :icon="Search"
          :disabled="!selectedProvider"
          @click="handleSearch"
        >
          {{ t('search.searchBtn') }}
        </el-button>
      </div>
      <p v-if="providerError" class="provider-error">{{ providerError }}</p>
      
      <div class="examples-section">
        <p class="examples-title">{{ authStore.isLoggedIn ? '智能推荐检索方向（基于你的研究兴趣）' : '智能推荐检索方向' }}</p>
        <div class="example-tags">
          <el-tag
            v-for="(example, index) in suggestedQueries"
            :key="index"
            class="example-tag"
            type="info"
            effect="plain"
            round
            @click="selectExample(example)"
          >
            {{ example }}
          </el-tag>
        </div>
      </div>

      <section v-if="authStore.isLoggedIn && (recommendationsLoading || recommendations.length)" class="discovery-section" v-loading="recommendationsLoading">
        <div class="discovery-heading"><span>为你发现</span><small>根据近期检索兴趣生成</small></div>
        <div class="recommendation-grid">
          <button v-for="paper in recommendations" :key="paper.id" class="recommendation-card" @click="openPaper(paper.id)">
            <strong>{{ paper.title }}</strong>
            <span>{{ paper.venue }} · {{ paper.year || '—' }}</span>
            <small>{{ paper.citationCount || 0 }} 次引用</small>
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped lang="scss">
.home-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: calc(100vh - 120px);
}

.search-section {
  width: 100%;
  max-width: 800px;
  text-align: center;
  transform: translateY(-10%);
}

.title {
  font-size: 56px;
  font-weight: 800;
  color: var(--text-primary);
  margin-bottom: 16px;
  letter-spacing: -1px;
}

.highlight {
  color: var(--primary-color);
}

.subtitle {
  font-size: 18px;
  color: var(--text-secondary);
  margin-bottom: 48px;
}

.search-box {
  --search-control-height: 56px;

  display: flex;
  align-items: stretch;
  gap: 10px;
  margin-bottom: 32px;
  border-radius: 8px;
  transition: all 0.3s ease;
  
  &:hover, &:focus-within {
    filter: drop-shadow(0 6px 14px rgba(63, 81, 181, 0.12));
  }
}

:deep(.el-input__wrapper) {
  padding: 8px 16px;
  font-size: 16px;
}
.search-input {
  flex: 1;
  height: var(--search-control-height);
}
.llm-provider-select {
  width: 230px;
  flex: 0 0 230px;
  height: var(--search-control-height);
}
:deep(.llm-provider-select .el-select__wrapper) {
  min-height: var(--search-control-height);
}
.search-box > .el-button {
  height: var(--search-control-height);
}
.provider-error { margin: -20px 0 24px; color: var(--el-color-danger); font-size: 13px; }

.examples-section {
  text-align: left;
  margin-top: 40px;
}
.discovery-section { margin-top: 42px; text-align: left; }
.discovery-heading { display: flex; align-items: baseline; gap: 10px; margin-bottom: 14px; color: var(--text-primary); font-size: 18px; font-weight: 700; }
.discovery-heading small { color: var(--text-secondary); font-size: 12px; font-weight: 400; }
.recommendation-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.recommendation-card { display: flex; min-width: 0; flex-direction: column; gap: 7px; padding: 15px; border: 1px solid var(--border-color); border-radius: 9px; background: var(--bg-surface); cursor: pointer; text-align: left; transition: .2s ease; }
.recommendation-card:hover { border-color: var(--primary-color); box-shadow: 0 5px 16px rgba(63, 81, 181, .12); transform: translateY(-2px); }
.recommendation-card strong { overflow: hidden; color: var(--text-primary); font-size: 14px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.recommendation-card span, .recommendation-card small { overflow: hidden; color: var(--text-secondary); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.recommendation-card small { color: #b88230; }
@media (max-width: 600px) {
  .search-box { flex-wrap: wrap; }
  .search-input { min-width: 100%; }
  .llm-provider-select { width: auto; flex: 1; }
  .recommendation-grid { grid-template-columns: 1fr; }
}

.examples-title {
  color: var(--text-secondary);
  font-size: 14px;
  margin-bottom: 12px;
}

.example-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.example-tag {
  cursor: pointer;
  padding: 6px 12px;
  height: auto;
  font-size: 14px;
  white-space: normal;
  text-align: left;
  line-height: 1.4;
  border-color: var(--border-color);
  color: var(--text-secondary);
  transition: all 0.2s ease;
  
  &:hover {
    color: var(--primary-color);
    border-color: var(--primary-color);
    background-color: rgba(63, 81, 181, 0.05);
  }
}
</style>
