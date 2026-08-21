<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { usePapersStore } from '@/stores/papers'
import { API_BASE } from '@/services/api'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const papersStore = usePapersStore()

const searchHistory = ref<{ id: number; query: string; searched_at: string }[]>([])
const browsingHistory = ref<{ id: number; paper_id: string; paper_title: string; viewed_at: string }[]>([])
const collections = ref<{ id: number; name: string; papers: { id: number; paper_id: string; paper_title: string }[] }[]>([])
const historyLoading = ref(false)
const papersLoading = ref(false)

onMounted(async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }
  // Load data in parallel
  historyLoading.value = true
  papersLoading.value = true
  await Promise.all([
    loadSearchHistory(),
    papersStore.fetchSavedPapers(),
    loadBrowsingHistory(),
    loadCollections(),
  ])
  historyLoading.value = false
  papersLoading.value = false
})

async function loadSearchHistory() {
  try {
    const res = await axios.get(`${API_BASE}/api/user/search-history`)
    searchHistory.value = res.data
  } catch (err) {
    console.error('Failed to load search history', err)
  }
}

async function loadBrowsingHistory() {
  try { browsingHistory.value = (await axios.get(`${API_BASE}/api/user/browsing-history`)).data } catch (err) { console.error('Failed to load browsing history', err) }
}

async function loadCollections() {
  try { collections.value = (await axios.get(`${API_BASE}/api/user/collections`)).data } catch (err) { console.error('Failed to load collections', err) }
}

function searchAgain(query: string) {
  router.push({ name: 'search-results', query: { q: query } })
}

async function removeFromLibrary(paperId: string) {
  try {
    await ElMessageBox.confirm('确定要从收藏中移除这篇论文吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await papersStore.removePaper(paperId)
    ElMessage.success(t('paper.unsaveSuccess'))
  } catch {
    // User cancelled
  }
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

function handleLogout() {
  authStore.logout()
  papersStore.clear()
  ElMessage.success(t('auth.logoutSuccess'))
  router.push('/')
}
</script>

<template>
  <div class="profile-container" v-if="authStore.isLoggedIn">
    <!-- Profile Header -->
    <div class="profile-header">
      <div class="avatar-section">
        <div class="avatar">
          <span class="avatar-letter">{{ authStore.user?.username?.charAt(0).toUpperCase() }}</span>
        </div>
        <div class="user-info">
          <h1 class="username">{{ authStore.user?.username }}</h1>
          <p class="user-email">{{ authStore.user?.email }}</p>
          <p class="member-since">
            <el-icon><Calendar /></el-icon>
            {{ $t('profile.memberSince') }}: {{ formatDate(authStore.user?.created_at || '') }}
          </p>
        </div>
      </div>
      <el-button type="danger" plain @click="handleLogout" :icon="SwitchButton">
        {{ $t('nav.logout') }}
      </el-button>
    </div>

    <el-row :gutter="24" class="content-section">
      <!-- Saved Papers -->
      <el-col :span="14">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-header">
              <div class="section-title">
                <el-icon color="var(--primary-color)"><Collection /></el-icon>
                <span>{{ $t('profile.savedPapers') }}</span>
                <el-badge :value="papersStore.savedPapers.length" class="count-badge" />
              </div>
            </div>
          </template>

          <div v-loading="papersLoading">
            <el-empty
              v-if="papersStore.savedPapers.length === 0 && !papersLoading"
              :description="$t('profile.noSavedPapers')"
            />
            <div
              v-for="paper in papersStore.savedPapers"
              :key="paper.paper_id"
              class="paper-item"
            >
              <div class="paper-info">
                <a
                  class="paper-title"
                  @click="router.push(`/paper/${paper.paper_id}`)"
                >
                  {{ paper.paper_title }}
                </a>
                <span class="paper-date">
                  {{ $t('profile.savedAt') }} {{ formatDate(paper.saved_at) }}
                </span>
              </div>
              <el-button
                size="small"
                type="danger"
                plain
                @click="removeFromLibrary(paper.paper_id)"
              >
                {{ $t('profile.removePaper') }}
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- Search History -->
      <el-col :span="10">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-header">
              <div class="section-title">
                <el-icon color="var(--primary-color)"><Clock /></el-icon>
                <span>{{ $t('profile.searchHistory') }}</span>
              </div>
            </div>
          </template>

          <div v-loading="historyLoading">
            <el-empty
              v-if="searchHistory.length === 0 && !historyLoading"
              :description="$t('profile.noSearchHistory')"
            />
            <div
              v-for="item in searchHistory"
              :key="item.id"
              class="history-item"
            >
              <div class="history-query-wrap">
                <el-icon class="history-icon"><Search /></el-icon>
                <div class="history-text">
                  <span class="history-query" @click="searchAgain(item.query)">
                    {{ item.query }}
                  </span>
                  <span class="history-date">{{ formatDate(item.searched_at) }}</span>
                </div>
              </div>
              <el-button
                size="small"
                text
                type="primary"
                @click="searchAgain(item.query)"
              >
                {{ $t('profile.searchAgain') }}
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="24" class="secondary-section">
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="section-card compact-card">
          <template #header><div class="section-title"><el-icon color="var(--primary-color)"><Folder /></el-icon><span>我的课题库</span></div></template>
          <el-empty v-if="collections.length === 0" description="尚未创建课题库" :image-size="68" />
          <div v-for="collection in collections" :key="collection.id" class="collection-item">
            <strong>{{ collection.name }}</strong><el-tag size="small">{{ collection.papers.length }} 篇</el-tag>
            <div v-for="item in collection.papers.slice(0, 3)" :key="item.id" class="collection-paper" @click="router.push(`/paper/${item.paper_id}`)">{{ item.paper_title }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="section-card compact-card">
          <template #header><div class="section-title"><el-icon color="var(--primary-color)"><View /></el-icon><span>最近浏览</span></div></template>
          <el-empty v-if="browsingHistory.length === 0" description="暂无浏览记录" :image-size="68" />
          <div v-for="item in browsingHistory" :key="item.id" class="browse-item" @click="router.push(`/paper/${item.paper_id}`)">
            <span>{{ item.paper_title }}</span><small>{{ formatDate(item.viewed_at) }}</small>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script lang="ts">
import { Calendar, Collection, Clock, Search, SwitchButton, Folder, View } from '@element-plus/icons-vue'
export { Calendar, Collection, Clock, Search, SwitchButton, Folder, View }
</script>

<style scoped lang="scss">
.profile-container {
  max-width: 1100px;
  margin: 0 auto;
}

.profile-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 32px;
  padding: 32px 40px;
  background: var(--bg-surface);
  border-radius: 16px;
  border: 1px solid var(--border-color);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

.avatar-section {
  display: flex;
  align-items: center;
  gap: 24px;
}

.avatar {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3f51b5, #7986cb);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.avatar-letter {
  font-size: 30px;
  font-weight: 800;
  color: white;
}

.username {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.user-email {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0 0 8px;
}

.member-since {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.content-section {
  margin-top: 0;
}
.secondary-section { margin-top: 24px; }
.compact-card { min-height: 260px; }
.collection-item { padding: 10px 0; border-bottom: 1px solid var(--border-color); }
.collection-item strong { margin-right: 8px; }
.collection-paper, .browse-item { cursor: pointer; color: var(--text-secondary); font-size: 13px; overflow: hidden; padding-top: 8px; text-overflow: ellipsis; white-space: nowrap; }
.collection-paper:hover, .browse-item:hover { color: var(--primary-color); }
.browse-item { display: flex; justify-content: space-between; gap: 12px; }
.browse-item small { flex: 0 0 auto; color: var(--text-secondary); }

.section-card {
  background: var(--bg-surface);
  border-radius: 12px;
  min-height: 400px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.count-badge {
  :deep(.el-badge__content) {
    position: static;
    transform: none;
    margin-left: 4px;
    font-size: 11px;
  }
}

.paper-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 0;
  border-bottom: 1px solid var(--border-color);

  &:last-child {
    border-bottom: none;
  }
}

.paper-info {
  flex: 1;
  min-width: 0;
}

.paper-title {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: var(--primary-color);
  cursor: pointer;
  line-height: 1.5;
  margin-bottom: 6px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;

  &:hover {
    text-decoration: underline;
  }
}

.paper-date {
  font-size: 12px;
  color: var(--text-secondary);
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-color);

  &:last-child {
    border-bottom: none;
  }
}

.history-query-wrap {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.history-icon {
  color: var(--text-secondary);
  flex-shrink: 0;
  margin-top: 2px;
}

.history-text {
  flex: 1;
  min-width: 0;
}

.history-query {
  display: block;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.4;
  cursor: pointer;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;

  &:hover {
    color: var(--primary-color);
  }
}

.history-date {
  display: block;
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}
</style>
