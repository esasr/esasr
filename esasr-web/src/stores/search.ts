import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'scholarseeker_search_cache_v5'
const CACHE_TTL_MS = 30 * 60 * 1000
const MAX_CACHE_ENTRIES = 8

export interface SearchViewState {
  selectedVenues: string[]
  yearFrom: number | null
  citationMinimum: number | null
  openAccessOnly: boolean
  sortBy: 'relevance' | 'date'
  sortOrder: 'desc' | 'asc'
  scrollY: number
}

interface SearchCacheEntry {
  query: string
  response: Record<string, any>
  createdAt: number
  viewState?: SearchViewState
}

function cacheKey(query: string, provider = '') {
  const normalizedQuery = query.trim().replace(/\s+/g, ' ').toLocaleLowerCase()
  return `${provider.trim().toLocaleLowerCase()}::${normalizedQuery}`
}

function loadEntries(): Record<string, SearchCacheEntry> {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '{}')
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

export const useSearchStore = defineStore('search', () => {
  const entries = ref<Record<string, SearchCacheEntry>>(loadEntries())

  function persist() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entries.value))
    } catch {
      const newest = Object.entries(entries.value)
        .sort(([, a], [, b]) => b.createdAt - a.createdAt)
        .slice(0, Math.max(1, Math.floor(MAX_CACHE_ENTRIES / 2)))
      entries.value = Object.fromEntries(newest)
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entries.value))
      } catch {
        // Storage may be disabled; in-memory caching still works for this tab.
      }
    }
  }

  function prune() {
    const now = Date.now()
    for (const [key, entry] of Object.entries(entries.value)) {
      if (now - entry.createdAt > CACHE_TTL_MS) delete entries.value[key]
    }
    const newest = Object.entries(entries.value)
      .sort(([, a], [, b]) => b.createdAt - a.createdAt)
      .slice(0, MAX_CACHE_ENTRIES)
    entries.value = Object.fromEntries(newest)
  }

  function get(query: string, provider = ''): SearchCacheEntry | null {
    prune()
    const entry = entries.value[cacheKey(query, provider)]
    persist()
    return entry || null
  }

  function set(query: string, provider: string, response: Record<string, any>) {
    const key = cacheKey(query, provider)
    const previous = entries.value[key]
    entries.value[key] = {
      query: query.trim(),
      response,
      createdAt: Date.now(),
      viewState: previous?.viewState,
    }
    prune()
    persist()
  }

  function saveViewState(query: string, provider: string, viewState: SearchViewState) {
    const entry = entries.value[cacheKey(query, provider)]
    if (!entry) return
    entry.viewState = viewState
    persist()
  }

  function remove(query: string, provider = '') {
    delete entries.value[cacheKey(query, provider)]
    persist()
  }

  return { get, set, saveViewState, remove }
})
