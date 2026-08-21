import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '../layout/MainLayout.vue'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        {
          path: '',
          name: 'home',
          component: HomeView,
          meta: { title: 'ScholarSeeker · 智能学术搜索' },
        },
        {
          path: 'search',
          name: 'search-results',
          component: () => import('../views/SearchResultsView.vue'),
          meta: { title: '搜索结果 · ScholarSeeker' },
        },
        {
          path: 'paper/:id',
          name: 'paper-detail',
          component: () => import('../views/PaperDetailView.vue'),
          meta: { title: '论文详情 · ScholarSeeker' },
        },
        {
          path: 'profile',
          name: 'profile',
          component: () => import('../views/ProfileView.vue'),
          meta: { requiresAuth: true, title: '个人中心 · ScholarSeeker' },
        },
      ]
    },
    {
      // Auth pages use a full-page layout (no MainLayout)
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { title: '登录 · ScholarSeeker' },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('../views/RegisterView.vue'),
      meta: { title: '注册 · ScholarSeeker' },
    },
  ],
})

// Route guard: redirect to login for auth-required routes
router.beforeEach((to) => {
  if (to.meta.requiresAuth) {
    const token = localStorage.getItem('scholarseeker_token')
    if (!token) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
  }
  return true
})

router.afterEach((to) => {
  const baseTitle = typeof to.meta.title === 'string' ? to.meta.title : 'ScholarSeeker · 智能学术搜索'
  if (to.name === 'search-results' && typeof to.query.q === 'string' && to.query.q.trim()) {
    document.title = `${to.query.q.trim()} · ScholarSeeker`
  } else {
    document.title = baseTitle
  }
})

export default router
