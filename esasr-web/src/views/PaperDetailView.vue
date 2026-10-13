<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Back, Document, Link } from '@element-plus/icons-vue'
import MotionIcon from '@/components/MotionIcon.vue'
import ReadingNav from '@/components/ReadingNav.vue'
import PaperRelationshipGraph from '@/components/PaperRelationshipGraph.vue'
import { useMediaQuery } from '@vueuse/core'
import { vReveal } from '@/directives/reveal'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { usePapersStore } from '@/stores/papers'
import { API_BASE } from '@/services/api'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const stackedLayout = useMediaQuery('(max-width: 1199px)')
const readingSections = computed(() => [
  { id: 'paper-abstract', label: t('paper.abstract') },
  { id: 'paper-network', label: t('paper.citationNetwork') },
  ...(stackedLayout.value ? [{ id: 'paper-related', label: t('paper.relatedPapers') }] : []),
])
const authStore = useAuthStore()
const papersStore = usePapersStore()

const paperId = computed(() => route.params.id as string)
const paper = ref<Record<string, any>>({})
const relatedPapers = ref<Record<string, any>[]>([])
const collections = ref<{ id: number; name: string }[]>([])
const selectedCollection = ref<number | null>(null)
const loading = ref(true)
const relatedLoading = ref(false)
const saveLoading = ref(false)

const isSaved = computed(() => papersStore.isSaved(paperId.value))
const citationText = computed(() => {
  const authors = paper.value.authors || ''
  const year = paper.value.year || 'n.d.'
  return `${authors} (${year}). ${paper.value.title || ''}. ${paper.value.venue || ''}.`
})

function goBack() {
  router.back()
}

function openPdf() {
  if (paper.value.pdfUrl) window.open(paper.value.pdfUrl, '_blank', 'noopener')
}

async function copyCitation() {
  try {
    await navigator.clipboard.writeText(citationText.value)
    ElMessage.success('引用信息已复制')
  } catch {
    ElMessage.info(citationText.value)
  }
}

async function handleSave() {
  if (!authStore.isLoggedIn) {
    try {
      await ElMessageBox.confirm(t('paper.loginToSave'), '', {
        confirmButtonText: t('nav.login'), cancelButtonText: '取消', type: 'info',
      })
      router.push({ name: 'login', query: { redirect: route.fullPath } })
    } catch { /* user cancelled */ }
    return
  }

  saveLoading.value = true
  try {
    if (isSaved.value) {
      await papersStore.removePaper(paperId.value)
      ElMessage.success(t('paper.unsaveSuccess'))
    } else {
      await papersStore.savePaper(paperId.value, paper.value.title, {
        title: paper.value.title, authors: paper.value.authors, authorDetails: paper.value.authorDetails,
        venue: paper.value.venue, year: paper.value.year, abstract: paper.value.abstract,
        citationCount: paper.value.citationCount, doi: paper.value.doi, url: paper.value.url,
      })
      ElMessage.success(t('paper.saveSuccess'))
    }
  } catch {
    ElMessage.error('操作失败，请稍后重试')
  } finally {
    saveLoading.value = false
  }
}

async function loadCollections() {
  if (!authStore.isLoggedIn) return
  try {
    const { data } = await axios.get(`${API_BASE}/api/user/collections`)
    collections.value = data
  } catch { /* collection access is optional */ }
}

async function addToCollection() {
  if (!authStore.isLoggedIn) {
    router.push({ name: 'login', query: { redirect: route.fullPath } })
    return
  }
  if (!selectedCollection.value) {
    try {
      const { value } = await ElMessageBox.prompt('输入课题库名称，例如“医学多模态大模型”', '新建课题库', { confirmButtonText: '创建', cancelButtonText: '取消' })
      const { data } = await axios.post(`${API_BASE}/api/user/collections`, { name: value })
      collections.value.unshift(data)
      selectedCollection.value = data.id
    } catch { return }
  }
  try {
    await axios.post(`${API_BASE}/api/user/collections/${selectedCollection.value}/papers`, { paper_id: paperId.value, paper_title: paper.value.title })
    ElMessage.success('已归入课题库')
  } catch { ElMessage.error('归档失败，请稍后重试') }
}

async function loadPaper() {
  loading.value = true
  relatedLoading.value = true
  paper.value = {}
  relatedPapers.value = []
  try {
    const [detailResult, relatedResult] = await Promise.allSettled([
      axios.get(`${API_BASE}/api/papers/${paperId.value}`),
      axios.get(`${API_BASE}/api/papers/${paperId.value}/related`, { params: { limit: 5 } }),
    ])
    if (detailResult.status === 'fulfilled') {
      paper.value = detailResult.value.data.data || {}
      if (paper.value.title) document.title = `${paper.value.title} · ESASR`
    }
    else ElMessage.error('文献详情加载失败，请稍后重试')
    if (relatedResult.status === 'fulfilled') relatedPapers.value = relatedResult.value.data.data || []
    if (authStore.isLoggedIn && paper.value.title) {
      axios.post(`${API_BASE}/api/user/browsing-history`, { paper_id: paperId.value, paper_title: paper.value.title }).catch(() => {})
      loadCollections()
    }
  } finally {
    loading.value = false
    relatedLoading.value = false
  }
}

function viewRelatedPaper(id: string) {
  router.push({ name: 'paper-detail', params: { id } })
}

watch(paperId, loadPaper, { immediate: true })
</script>

<template>
  <main class="paper-detail-container" v-loading="loading">
    <el-button :icon="Back" text class="back-btn" @click="goBack">{{ t('paper.back') }}</el-button>

    <section v-if="!loading && paper.title" class="paper-header">
      <div class="header-main">
        <p class="eyebrow">ACADEMIC PAPER · {{ paper.type || 'work' }}</p>
        <h1 class="paper-title">{{ paper.title }}</h1>
        <p class="authors">{{ paper.authors || 'Unknown authors' }}</p>
        <div class="paper-tags">
          <el-tag effect="plain">{{ paper.venue }}</el-tag>
          <el-tag v-if="paper.year" type="info" effect="plain">{{ paper.year }}</el-tag>
          <el-tag v-if="paper.isOpenAccess" type="success" effect="plain">开放获取</el-tag>
          <el-tag v-if="paper.doi" type="warning" effect="plain">DOI: {{ paper.doi }}</el-tag>
        </div>
      </div>
      <div class="action-buttons">
        <el-button type="primary" :icon="Document" :disabled="!paper.pdfUrl" @click="openPdf">{{ t('paper.viewPdf') }}</el-button>
        <el-button :icon="Link" @click="copyCitation">{{ t('paper.cite') }}</el-button>
        <el-button :type="isSaved ? 'success' : 'default'" :loading="saveLoading" :aria-pressed="isSaved" @click="handleSave">
          <MotionIcon :name="isSaved ? 'check' : 'bookmark'" class="save-icon" />
          {{ isSaved ? t('paper.unsave') : t('paper.save') }}
        </el-button>
        <el-select v-if="authStore.isLoggedIn" v-model="selectedCollection" clearable placeholder="归入课题库" class="collection-select" @change="addToCollection">
          <el-option v-for="collection in collections" :key="collection.id" :label="collection.name" :value="collection.id" />
        </el-select>
        <el-button v-if="authStore.isLoggedIn" @click="addToCollection">归档</el-button>
      </div>
    </section>

    <section v-if="!loading && paper.title" class="metric-grid" aria-label="文献实时指标">
      <div class="metric"><strong>{{ paper.citationCount ?? 0 }}</strong><span>实时引用次数</span></div>
      <div class="metric"><strong>{{ paper.referencedWorksCount ?? 0 }}</strong><span>参考文献</span></div>
      <div class="metric"><strong>{{ paper.relatedWorksCount ?? 0 }}</strong><span>关联研究</span></div>
      <div class="metric"><strong>{{ paper.publicationDate || paper.year || '—' }}</strong><span>发表日期</span></div>
    </section>

    <ReadingNav v-if="!loading && paper.title" :sections="readingSections" />
    <el-row v-if="!loading && paper.title" :gutter="24" class="content-section">
      <el-col :xs="24" :lg="16">
        <el-card id="paper-abstract" v-reveal tabindex="-1" shadow="never" class="content-card">
          <template #header>
            <div class="card-header">
              <span class="card-header-icon abstract-icon" aria-hidden="true">
                <MotionIcon name="document" :size="16" />
              </span>
              <span>{{ t('paper.abstract') }}</span>
            </div>
          </template>
          <p class="abstract-text">{{ paper.abstract || 'No abstract available.' }}</p>
          <div v-if="paper.concepts?.length" class="concepts">
            <span>研究主题</span>
            <el-tag v-for="concept in paper.concepts" :key="concept" size="small" effect="plain">{{ concept }}</el-tag>
          </div>
        </el-card>

        <el-card id="paper-network" v-reveal tabindex="-1" shadow="never" class="content-card graph-card">
          <template #header>
            <div class="card-header">
              <span class="card-header-icon graph-icon" aria-hidden="true">
                <MotionIcon name="graph" :size="16" />
              </span>
              <span>{{ t('paper.citationNetwork') }}</span>
              <small>点击卡片预览 · 按关系探索</small>
            </div>
          </template>
          <PaperRelationshipGraph :paper-id="paperId" :paper="paper" :related-papers="relatedPapers" @open-paper="viewRelatedPaper" />
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="8" class="sidebar-column">
        <el-card id="paper-related" tabindex="-1" shadow="never" class="content-card related-card">
          <template #header><div class="card-header">{{ t('paper.relatedPapers') }}<small>基于关联图谱实时推荐</small></div></template>
          <div v-loading="relatedLoading" class="related-list">
            <button v-for="item in relatedPapers" :key="item.id" class="related-item" @click="viewRelatedPaper(item.id)">
              <span class="related-title">{{ item.title }}</span>
              <span class="related-meta">{{ item.authors }} · {{ item.venue }} · {{ item.year || '—' }}</span>
              <span class="related-citations">{{ item.citationCount || 0 }} 次引用</span>
            </button>
            <el-empty v-if="!relatedLoading && relatedPapers.length === 0" description="暂无可用关联文献" :image-size="72" />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </main>
</template>

<style scoped lang="scss">
.paper-detail-container { max-width: var(--page-width); margin: 0 auto; padding-bottom: 36px; }
.back-btn { margin-bottom: 18px; }
.paper-header { display: grid; grid-template-columns: minmax(0, 1fr) minmax(240px, 320px); gap: 28px; margin-bottom: 24px; }
.header-main { min-width: 0; }
.eyebrow { margin: 0 0 8px; color: #6d7e98; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
.paper-title { margin: 0 0 12px; color: var(--text-primary); font-size: clamp(25px, 3vw, 34px); line-height: 1.25; }
.authors { margin: 0 0 14px; color: var(--primary-color); font-size: 15px; line-height: 1.6; }
.paper-tags, .action-buttons, .concepts { display: flex; flex-wrap: wrap; gap: 8px; }
.collection-select { width: 142px; }
.action-buttons { flex: 0 0 auto; align-content: flex-start; justify-content: flex-end; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--border-color); border-radius: 10px; margin-bottom: 24px; overflow: hidden; background: var(--bg-surface); }
.metric { display: flex; min-width: 0; flex-direction: column; gap: 5px; padding: 17px 20px; border-right: 1px solid var(--border-color); }
.metric:last-child { border-right: 0; }
.metric strong { color: var(--primary-color); font-size: 22px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.metric span { color: var(--text-secondary); font-size: 12px; }
.content-card { margin-bottom: 24px; border-radius: 10px; background: var(--bg-surface); }
.card-header { display: flex; align-items: center; gap: 8px; color: var(--text-primary); font-size: 16px; font-weight: 650; }
.card-header-icon { display: inline-flex; width: 30px; height: 30px; flex: 0 0 30px; align-items: center; justify-content: center; border: 1px solid transparent; border-radius: 8px; }
.card-header-icon .el-icon { width: 16px; height: 16px; font-size: 16px; }
.card-header-icon :deep(svg) { width: 1em; height: 1em; }
.abstract-icon { border-color: rgba(63, 81, 181, .14); background: rgba(63, 81, 181, .08); color: #3f51b5; }
.graph-icon { border-color: rgba(45, 139, 126, .16); background: rgba(45, 139, 126, .09); color: #2d8b7e; }
.card-header small { margin-left: auto; color: var(--text-secondary); font-size: 12px; font-weight: 400; }
.abstract-text { margin: 0; color: var(--text-primary); font-size: 15px; line-height: 1.9; text-align: left; white-space: pre-line; overflow-wrap: anywhere; }
.concepts { align-items: center; margin-top: 22px; padding-top: 16px; border-top: 1px solid var(--border-color); }
.concepts > span { margin-right: 4px; color: var(--text-secondary); font-size: 13px; }
.graph-container { height: 520px; position: relative; display: flex; align-items: center; justify-content: center; overflow: hidden; border-radius: 7px; background: var(--bg-color); }
.graph-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; margin-top: 12px; color: var(--text-secondary); font-size: 12px; }
.center-dot, .related-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.center-dot { background: #3f51b5; }.related-dot { background: #5aa89e; }
.related-item { display: flex; width: 100%; flex-direction: column; gap: 7px; padding: 14px 0; border: 0; border-bottom: 1px solid var(--border-color); background: transparent; cursor: pointer; text-align: left; }
.related-item:first-child { padding-top: 0; }
.related-item:last-child { border-bottom: 0; }
.related-item:hover .related-title { color: var(--primary-color); }
.related-title { color: var(--text-primary); font-size: 14px; font-weight: 600; line-height: 1.45; transition: color .2s; }
.related-meta { overflow: hidden; color: var(--text-secondary); font-size: 12px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.related-citations { color: #c18016; font-size: 12px; }
.save-icon { margin-right: 7px; }
.paper-tags :deep(.el-tag) { height: auto; min-height: 24px; white-space: normal; overflow-wrap: anywhere; line-height: 1.5; padding-block: 3px; }
.paper-title { overflow-wrap: anywhere; text-wrap: pretty; }
.content-section > .el-col { min-width: 0; }
.content-card { scroll-margin-top: calc(var(--header-height) + 78px); }
.related-card { position: sticky; top: calc(var(--header-height) + 78px); max-height: calc(100dvh - var(--header-height) - 96px); overflow-y: auto; scrollbar-width: thin; }
.card-header { flex-wrap: wrap; }
.card-header small { line-height: 1.5; }
.related-meta { white-space: normal; overflow-wrap: anywhere; }
.graph-container { height: clamp(320px, 48vh, 520px); }
@media (max-width: 1199px) { .related-card { position: static; max-height: none; } }
@media (max-width: 768px) { .paper-header { grid-template-columns: minmax(0, 1fr); gap: 20px; } .action-buttons { justify-content: flex-start; } .metric-grid { grid-template-columns: repeat(2, 1fr); } .metric:nth-child(2) { border-right: 0; } .metric:nth-child(-n+2) { border-bottom: 1px solid var(--border-color); } .sidebar-column { margin-top: 0; } }
</style>
