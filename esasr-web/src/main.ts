import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import i18n from './locales'

import './assets/main.scss'

// A browser may keep an older HTML shell while a deployment replaces its
// content-hashed lazy chunks. Recover once by loading the current asset map.
const staleChunkRecoveryKey = 'esasr:stale-chunk-recovery'
window.addEventListener('vite:preloadError', (event) => {
  event.preventDefault()
  const lastRecovery = Number(sessionStorage.getItem(staleChunkRecoveryKey) || 0)
  if (Date.now() - lastRecovery > 15_000) {
    sessionStorage.setItem(staleChunkRecoveryKey, String(Date.now()))
    window.location.reload()
  }
})

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ElementPlus)
app.use(i18n)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// Restore auth state from localStorage before mounting
import { useAuthStore } from './stores/auth'
const authStore = useAuthStore()
authStore.initFromStorage().then(() => {
  app.mount('#app')
})
