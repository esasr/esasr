<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useColorMode } from '@vueuse/core'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { usePapersStore } from '@/stores/papers'

const router = useRouter()
const route = useRoute()
const { locale } = useI18n()
const { t } = useI18n()
const colorMode = useColorMode({
  emitAuto: true,
})
const authStore = useAuthStore()
const papersStore = usePapersStore()

const activeMenu = computed(() => route.path)

const handleSelect = (key: string) => {
  if (key !== route.path) {
    void router.push(key)
  }
}

const toggleLanguage = (lang: string) => {
  locale.value = lang
}

const toggleTheme = (mode: 'auto' | 'light' | 'dark') => {
  colorMode.value = mode
}

const handleUserCommand = async (command: string) => {
  if (command === 'profile') {
    router.push('/profile')
  } else if (command === 'logout') {
    authStore.logout()
    papersStore.clear()
    ElMessage.success(t('auth.logoutSuccess'))
    router.push('/')
  }
}
</script>

<template>
  <el-container class="layout-container">
    <el-header class="header">
      <div class="logo" @click="router.push('/')">
        <el-icon :size="24" color="var(--primary-color)"><Reading /></el-icon>
        <span class="logo-text">ScholarSeeker</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        class="nav-menu"
        mode="horizontal"
        :ellipsis="false"
        @select="handleSelect"
      >
        <el-menu-item index="/">{{ $t('nav.home') }}</el-menu-item>
        <el-menu-item index="/about">{{ $t('nav.about') }}</el-menu-item>
      </el-menu>
      
      <div class="header-actions">
        <!-- Theme switcher -->
        <el-dropdown @command="toggleTheme" class="action-dropdown">
          <span class="el-dropdown-link">
            <el-icon v-if="colorMode === 'dark'"><Moon /></el-icon>
            <el-icon v-else-if="colorMode === 'light'"><Sunny /></el-icon>
            <el-icon v-else><Monitor /></el-icon>
            {{ $t('nav.theme') }}<el-icon class="el-icon--right"><arrow-down /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="auto">{{ $t('nav.themeSystem') }}</el-dropdown-item>
              <el-dropdown-item command="light">{{ $t('nav.themeLight') }}</el-dropdown-item>
              <el-dropdown-item command="dark">{{ $t('nav.themeDark') }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <!-- Language switcher -->
        <el-dropdown @command="toggleLanguage" class="action-dropdown">
          <span class="el-dropdown-link">
            {{ $t('nav.language') }}<el-icon class="el-icon--right"><arrow-down /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="zh">中文</el-dropdown-item>
              <el-dropdown-item command="en">English</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <!-- ── Auth Section ── -->
        <!-- Guest: show login + register buttons -->
        <template v-if="!authStore.isLoggedIn">
          <el-button text class="auth-btn" @click="router.push('/login')">
            {{ $t('nav.login') }}
          </el-button>
          <el-button type="primary" class="auth-btn-primary" @click="router.push('/register')">
            {{ $t('nav.register') }}
          </el-button>
        </template>

        <!-- Logged in: show user avatar dropdown -->
        <template v-else>
          <el-dropdown @command="handleUserCommand" class="user-dropdown">
            <div class="user-avatar-wrap">
              <div class="user-avatar">
                {{ authStore.user?.username?.charAt(0).toUpperCase() }}
              </div>
              <span class="username-label">{{ authStore.user?.username }}</span>
              <el-icon class="el-icon--right"><arrow-down /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><User /></el-icon>
                  {{ $t('nav.profile') }}
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>
                  {{ $t('nav.logout') }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </div>
    </el-header>
    
    <el-main class="main-content">
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped lang="scss">
.layout-container {
  min-height: 100vh;
}

.header {
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--border-color);
  background-color: var(--bg-surface);
  padding: 0 40px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  margin-right: 40px;
}

.logo-text {
  font-size: 20px;
  font-weight: 700;
  color: var(--primary-color);
}

.nav-menu {
  border-bottom: none;
  flex: 1;
  background-color: transparent;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.action-dropdown {
  cursor: pointer;
}

.el-dropdown-link {
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 4px;
}

.auth-btn {
  color: var(--text-primary);
  font-size: 14px;
  padding: 0 12px;

  &:hover {
    color: var(--primary-color);
  }
}

.auth-btn-primary {
  font-size: 14px;
  padding: 8px 20px;
  border-radius: 8px;
  background: linear-gradient(135deg, #3f51b5, #5c6bc0);
  border: none;
  font-weight: 600;
  transition: all 0.25s;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(63, 81, 181, 0.35);
  }
}

.user-dropdown {
  cursor: pointer;
}

.user-avatar-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 10px;
  transition: background 0.2s;

  &:hover {
    background: rgba(63, 81, 181, 0.08);
  }
}

.user-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3f51b5, #7986cb);
  color: white;
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.username-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.main-content {
  background-color: var(--bg-color);
  padding: 24px 40px;
}

@media (max-width: 760px) {
  .header {
    padding: 0 14px;
  }

  .logo {
    margin-right: 10px;
  }

  .header-actions {
    gap: 8px;
  }

  .auth-btn,
  .auth-btn-primary {
    display: none;
  }

  .main-content {
    padding: 20px 24px;
  }
}

@media (max-width: 480px) {
  .logo-text {
    display: none;
  }

  .logo {
    margin-right: 4px;
  }

  .action-dropdown:first-child {
    display: none;
  }
}
</style>
