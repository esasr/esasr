<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { usePapersStore } from '@/stores/papers'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const papersStore = usePapersStore()

const loading = ref(false)
const formRef = ref()

const form = reactive({
  email: '',
  password: '',
})

const rules = {
  email: [
    { required: true, message: () => t('auth.emailRequired'), trigger: 'blur' },
    { type: 'email', message: () => t('auth.emailInvalid'), trigger: 'blur' },
  ],
  password: [
    { required: true, message: () => t('auth.passwordRequired'), trigger: 'blur' },
    { min: 6, message: () => t('auth.passwordMin'), trigger: 'blur' },
  ],
}

const handleLogin = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    loading.value = true
    try {
      await authStore.login(form.email, form.password)
      await papersStore.fetchSavedIds()
      ElMessage.success(t('auth.loginSuccess', { name: authStore.user?.username }))
      // Redirect to the originally intended page or home
      const redirect = route.query.redirect as string
      router.push(redirect || '/')
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Login failed'
      ElMessage.error(msg)
    } finally {
      loading.value = false
    }
  })
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <!-- Decorative left panel -->
      <div class="auth-brand">
        <div class="brand-content">
          <div class="brand-icon">
            <el-icon :size="48" color="white"><Reading /></el-icon>
          </div>
          <h2 class="brand-name">ScholarSeeker</h2>
          <p class="brand-tagline">{{ $t('home.subtitle') }}</p>
          <div class="brand-features">
            <div class="feature-item">
              <el-icon><Search /></el-icon>
              <span>智能文献检索</span>
            </div>
            <div class="feature-item">
              <el-icon><Collection /></el-icon>
              <span>个人文献收藏</span>
            </div>
            <div class="feature-item">
              <el-icon><DataAnalysis /></el-icon>
              <span>个性化推荐</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Form panel -->
      <div class="auth-form-panel">
        <div class="form-header">
          <h1 class="form-title">{{ $t('auth.loginTitle') }}</h1>
          <p class="form-subtitle">{{ $t('auth.loginSubtitle') }}</p>
        </div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          class="login-form"
          size="large"
          @keyup.enter="handleLogin"
        >
          <el-form-item prop="email">
            <el-input
              v-model="form.email"
              :placeholder="$t('auth.emailPlaceholder')"
              type="email"
              :prefix-icon="Message"
              autocomplete="email"
            />
          </el-form-item>

          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              :placeholder="$t('auth.passwordPlaceholder')"
              type="password"
              :prefix-icon="Lock"
              show-password
              autocomplete="current-password"
            />
          </el-form-item>

          <el-button
            type="primary"
            class="submit-btn"
            :loading="loading"
            @click="handleLogin"
          >
            {{ $t('auth.loginBtn') }}
          </el-button>
        </el-form>

        <div class="form-footer">
          <span class="footer-text">{{ $t('auth.noAccount') }}</span>
          <router-link to="/register" class="footer-link">{{ $t('auth.registerLink') }}</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { Message, Lock, Search, Collection, DataAnalysis } from '@element-plus/icons-vue'
export { Message, Lock, Search, Collection, DataAnalysis }
</script>

<style scoped lang="scss">
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-color);
  padding: 20px;
}

.auth-card {
  display: flex;
  width: 100%;
  max-width: 900px;
  min-height: 560px;
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.12);
}

.auth-brand {
  flex: 0 0 42%;
  background: linear-gradient(145deg, #3f51b5 0%, #5c6bc0 50%, #7986cb 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 40px;
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    width: 300px;
    height: 300px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.06);
    top: -80px;
    right: -80px;
  }

  &::after {
    content: '';
    position: absolute;
    width: 200px;
    height: 200px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.04);
    bottom: -60px;
    left: -40px;
  }
}

.brand-content {
  text-align: center;
  color: white;
  position: relative;
  z-index: 1;
}

.brand-icon {
  width: 80px;
  height: 80px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 24px;
  backdrop-filter: blur(10px);
}

.brand-name {
  font-size: 28px;
  font-weight: 800;
  margin: 0 0 12px;
  letter-spacing: -0.5px;
}

.brand-tagline {
  font-size: 14px;
  opacity: 0.85;
  line-height: 1.6;
  margin-bottom: 40px;
}

.brand-features {
  display: flex;
  flex-direction: column;
  gap: 16px;
  text-align: left;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
  opacity: 0.9;
  background: rgba(255, 255, 255, 0.1);
  padding: 10px 16px;
  border-radius: 10px;
  backdrop-filter: blur(5px);
}

.auth-form-panel {
  flex: 1;
  background: var(--bg-surface);
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 56px 48px;
}

.form-header {
  margin-bottom: 40px;
}

.form-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.form-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

.login-form {
  :deep(.el-form-item) {
    margin-bottom: 20px;
  }

  :deep(.el-input__wrapper) {
    border-radius: 10px;
    padding: 4px 16px;
    box-shadow: 0 0 0 1px var(--border-color) inset;
    transition: box-shadow 0.2s;

    &:hover, &.is-focus {
      box-shadow: 0 0 0 2px var(--primary-color) inset;
    }
  }
}

.submit-btn {
  width: 100%;
  height: 48px;
  border-radius: 10px;
  font-size: 16px;
  font-weight: 600;
  margin-top: 8px;
  background: linear-gradient(135deg, #3f51b5, #5c6bc0);
  border: none;
  transition: all 0.3s ease;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 20px rgba(63, 81, 181, 0.35);
  }
}

.form-footer {
  margin-top: 32px;
  text-align: center;
  font-size: 14px;
}

.footer-text {
  color: var(--text-secondary);
  margin-right: 6px;
}

.footer-link {
  color: var(--primary-color);
  font-weight: 600;
  text-decoration: none;
  transition: opacity 0.2s;

  &:hover {
    opacity: 0.8;
    text-decoration: underline;
  }
}
</style>
