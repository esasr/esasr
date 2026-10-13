import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'
import { API_BASE } from '@/services/api'

const TOKEN_KEY = 'scholarseeker_token'

export interface UserProfile {
  id: number
  username: string
  email: string
  created_at: string
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserProfile | null>(null)
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))

  const isLoggedIn = computed(() => !!token.value && !!user.value)

  /** Set the auth token into axios default headers and localStorage */
  function setToken(t: string | null) {
    token.value = t
    if (t) {
      localStorage.setItem(TOKEN_KEY, t)
      axios.defaults.headers.common['Authorization'] = `Bearer ${t}`
    } else {
      localStorage.removeItem(TOKEN_KEY)
      delete axios.defaults.headers.common['Authorization']
    }
  }

  /** On app startup, restore auth state from localStorage */
  async function initFromStorage() {
    const savedToken = localStorage.getItem(TOKEN_KEY)
    if (!savedToken) return
    setToken(savedToken)
    try {
      const res = await axios.get(`${API_BASE}/api/auth/me`)
      user.value = res.data
    } catch {
      // Token expired or invalid — clear it
      setToken(null)
      user.value = null
    }
  }

  async function register(username: string, email: string, password: string) {
    const res = await axios.post(`${API_BASE}/api/auth/register`, {
      username,
      email,
      password,
    })
    setToken(res.data.access_token)
    user.value = res.data.user
    return res.data
  }

  async function login(email: string, password: string) {
    const res = await axios.post(`${API_BASE}/api/auth/login`, {
      email,
      password,
    })
    setToken(res.data.access_token)
    user.value = res.data.user
    return res.data
  }

  function logout() {
    setToken(null)
    user.value = null
  }

  // Initialize axios header if token already exists
  if (token.value) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${token.value}`
  }

  return { user, token, isLoggedIn, register, login, logout, initFromStorage }
})
