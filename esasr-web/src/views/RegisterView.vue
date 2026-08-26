<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { usePapersStore } from '@/stores/papers'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const papersStore = usePapersStore()

const loading = ref(false)
const formRef = ref()

const form = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
})

const validateConfirmPassword = (_: any, value: string, callback: Function) => {
  if (!value) {
    callback(new Error(t('auth.confirmPasswordRequired')))
  } else if (value !== form.password) {
    callback(new Error(t('auth.passwordMismatch')))
  } else {
    callback()
  }
}

const rules = {
  username: [
    { required: true, message: () => t('auth.usernameRequired'), trigger: 'blur' },
    { min: 2, message: () => t('auth.usernameMin'), trigger: 'blur' },
  ],
  email: [
    { required: true, message: () => t('auth.emailRequired'), trigger: 'blur' },
    { type: 'email', message: () => t('auth.emailInvalid'), trigger: 'blur' },
  ],
  password: [
    { required: true, message: () => t('auth.passwordRequired'), trigger: 'blur' },
    { min: 6, message: () => t('auth.passwordMin'), trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, validator: validateConfirmPassword, trigger: 'blur' },
  ],
}

const handleRegister = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    loading.value = true
    try {
      await authStore.register(form.username, form.email, form.password)
      await papersStore.fetchSavedIds()
      ElMessage.success(t('auth.registerSuccess'))
      router.push('/')
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Registration failed'
      ElMessage.error(msg)
    } finally {
      loading.value = false
    }
  })
}

// Password strength indicator
const passwordStrength = (pwd: string): { level: number; text: string; color: string } => {
  if (!pwd) return { level: 0, text: '', color: '' }
  let score = 0
  if (pwd.length >= 6) score++
  if (pwd.length >= 10) score++
  if (/[A-Z]/.test(pwd)) score++
  if (/[0-9]/.test(pwd)) score++
  if (/[^A-Za-z0-9]/.test(pwd)) score++

  if (score <= 1) return { level: 1, text: '弱', color: '#f56c6c' }
  if (score <= 3) return { level: 2, text: '中', color: '#e6a23c' }
  return { level: 3, text: '强', color: '#67c23a' }
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
          <h2 class="brand-name">ESASR</h2>
          <p class="brand-tagline">{{ $t('auth.registerSubtitle') }}</p>
          <div class="steps-list">
            <div class="step-item">
              <span class="step-num">01</span>
              <span>创建您的专属账号</span>
            </div>
            <div class="step-item">
              <span class="step-num">02</span>
              <span>搜索感兴趣的论文</span>
            </div>
            <div class="step-item">
              <span class="step-num">03</span>
              <span>收藏与追踪文献动态</span>
            </div>
            <div class="step-item">
              <span class="step-num">04</span>
              <span>享受个性化智能推荐</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Form panel -->
      <div class="auth-form-panel">
        <div class="form-header">
          <h1 class="form-title">{{ $t('auth.registerTitle') }}</h1>
          <p class="form-subtitle">{{ $t('auth.registerSubtitle') }}</p>
        </div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          class="register-form"
          size="large"
        >
          <el-form-item prop="username">
            <el-input
              v-model="form.username"
              :placeholder="$t('auth.usernamePlaceholder')"
              :prefix-icon="User"
              autocomplete="username"
            />
          </el-form-item>

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
              autocomplete="new-password"
            />
            <!-- Password strength bar -->
            <div class="strength-bar" v-if="form.password">
              <div class="strength-segments">
                <div
                  v-for="i in 3"
                  :key="i"
                  class="segment"
                  :class="{ active: passwordStrength(form.password).level >= i }"
                  :style="{ backgroundColor: passwordStrength(form.password).level >= i ? passwordStrength(form.password).color : '' }"
                />
              </div>
              <span class="strength-text" :style="{ color: passwordStrength(form.password).color }">
                {{ passwordStrength(form.password).text }}
              </span>
            </div>
          </el-form-item>

          <el-form-item prop="confirmPassword">
            <el-input
              v-model="form.confirmPassword"
              :placeholder="$t('auth.confirmPasswordPlaceholder')"
              type="password"
              :prefix-icon="Lock"
              show-password
              autocomplete="new-password"
              @keyup.enter="handleRegister"
            />
          </el-form-item>

          <el-button
            type="primary"
            class="submit-btn"
            :loading="loading"
            @click="handleRegister"
          >
            {{ $t('auth.registerBtn') }}
          </el-button>
        </el-form>

        <div class="form-footer">
          <span class="footer-text">{{ $t('auth.hasAccount') }}</span>
          <router-link to="/login" class="footer-link">{{ $t('auth.loginLink') }}</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { User, Message, Lock } from '@element-plus/icons-vue'
export { User, Message, Lock }
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
  min-height: 600px;
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
  font-size: 13px;
  opacity: 0.85;
  line-height: 1.6;
  margin-bottom: 36px;
}

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  text-align: left;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
  opacity: 0.9;
}

.step-num {
  font-size: 12px;
  font-weight: 800;
  background: rgba(255, 255, 255, 0.2);
  color: white;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.auth-form-panel {
  flex: 1;
  background: var(--bg-surface);
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 48px 48px;
}

.form-header {
  margin-bottom: 32px;
}

.form-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.form-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.register-form {
  :deep(.el-form-item) {
    margin-bottom: 16px;
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

.strength-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.strength-segments {
  display: flex;
  gap: 4px;
  flex: 1;
}

.segment {
  flex: 1;
  height: 4px;
  border-radius: 2px;
  background: var(--border-color);
  transition: background-color 0.3s;

  &.active {
    background: #67c23a;
  }
}

.strength-text {
  font-size: 12px;
  font-weight: 600;
  min-width: 20px;
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
  margin-top: 24px;
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
