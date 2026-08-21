import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'
import { useAuthStore } from './auth'
import { API_BASE } from '@/services/api'

export interface SavedPaper {
  id: number
  paper_id: string
  paper_title: string
  paper_data: string | null
  saved_at: string
}

export const usePapersStore = defineStore('papers', () => {
  const savedPaperIds = ref<Set<string>>(new Set())
  const savedPapers = ref<SavedPaper[]>([])

  /** Fetch saved paper IDs for fast bookmark checking */
  async function fetchSavedIds() {
    const auth = useAuthStore()
    if (!auth.isLoggedIn) return
    try {
      const res = await axios.get(`${API_BASE}/api/user/saved-papers/ids`)
      savedPaperIds.value = new Set(res.data.ids)
    } catch (err) {
      console.error('Failed to fetch saved paper IDs', err)
    }
  }

  /** Fetch full saved papers list (for profile page) */
  async function fetchSavedPapers() {
    const auth = useAuthStore()
    if (!auth.isLoggedIn) return
    try {
      const res = await axios.get(`${API_BASE}/api/user/saved-papers`)
      savedPapers.value = res.data
    } catch (err) {
      console.error('Failed to fetch saved papers', err)
    }
  }

  async function savePaper(paperId: string, paperTitle: string, paperData?: object) {
    const res = await axios.post(`${API_BASE}/api/user/saved-papers`, {
      paper_id: paperId,
      paper_title: paperTitle,
      paper_data: paperData ? JSON.stringify(paperData) : null,
    })
    savedPaperIds.value.add(paperId)
    savedPapers.value.unshift(res.data)
    return res.data
  }

  async function removePaper(paperId: string) {
    await axios.delete(`${API_BASE}/api/user/saved-papers/${paperId}`)
    savedPaperIds.value.delete(paperId)
    savedPapers.value = savedPapers.value.filter(p => p.paper_id !== paperId)
  }

  function isSaved(paperId: string): boolean {
    return savedPaperIds.value.has(paperId)
  }

  function clear() {
    savedPaperIds.value = new Set()
    savedPapers.value = []
  }

  return { savedPaperIds, savedPapers, fetchSavedIds, fetchSavedPapers, savePaper, removePaper, isSaved, clear }
})
