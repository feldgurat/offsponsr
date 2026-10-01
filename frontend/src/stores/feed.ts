import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import type { FeedPage, PostCard, PostDetails } from '@/api/types'

/** What narrows a project's feed down and orders it. */
export interface FeedFilters {
  order: 'desc' | 'asc'
  /** The first and the last day of the period, as YYYY-MM-DD in the user's time zone. */
  from: string | null
  to: string | null
  content: 'audio' | 'video' | null
  hideClosed: boolean
  hideDeleted: boolean
  /** Whether the posts come with their texts (the stream view shows them). */
  withText: boolean
}

function dayStart(day: string): string {
  const [year, month, date] = day.split('-').map(Number)
  return new Date(year, month - 1, date).toISOString()
}

function dayEnd(day: string): string {
  const [year, month, date] = day.split('-').map(Number)
  return new Date(year, month - 1, date, 23, 59, 59, 999).toISOString()
}

/**
 * The posts of the project on screen. Kept in a store, not in the page, so that coming back
 * from a post finds the feed as it was left, without a reload.
 */
export const useFeedStore = defineStore('feed', () => {
  const posts = ref<PostCard[]>([])
  const total = ref(0)
  const perPage = ref(20)
  const firstPage = ref(1)
  const lastPage = ref(0)
  const loading = ref(false)
  const failed = ref(false)

  /** What the posts on hand were asked with; a different question starts the feed over. */
  let key = ''
  let params: Record<string, string | number | boolean | null> = {}
  let projectId = 0
  /** The last page asked for so far; it is on its way if it is not on hand yet. */
  let wantedLast = 0
  /** Counts the loads, so that an answer to a question no longer asked is dropped. */
  let generation = 0

  const pages = computed(() => Math.max(1, Math.ceil(total.value / perPage.value)))

  async function fetchPage(page: number): Promise<FeedPage> {
    return api.get<FeedPage>(`/projects/${projectId}/posts`, { ...params, page })
  }

  /** Show the pages `first..last` of the project's feed, loading only what isn't on hand. */
  async function show(project: number, filters: FeedFilters, first: number, last: number) {
    const wanted = JSON.stringify([project, filters])
    const extends_ = wanted === key && first === firstPage.value && last >= lastPage.value
    if (extends_ && last <= wantedLast && !failed.value) {
      // On hand already, or being loaded right now.
      return
    }

    wantedLast = last
    generation += 1
    const mine = generation
    if (!extends_) {
      key = wanted
      projectId = project
      params = {
        order: filters.order,
        date_from: filters.from ? dayStart(filters.from) : null,
        date_to: filters.to ? dayEnd(filters.to) : null,
        content: filters.content,
        hide_closed: filters.hideClosed,
        hide_deleted: filters.hideDeleted,
        with_text: filters.withText,
      }
      posts.value = []
      firstPage.value = first
      lastPage.value = first - 1
    }

    loading.value = true
    failed.value = false
    try {
      for (let page = lastPage.value + 1; page <= last; page += 1) {
        const answer = await fetchPage(page)
        if (mine !== generation) {
          return
        }
        posts.value = [...posts.value, ...answer.posts]
        total.value = answer.total
        perPage.value = answer.per_page
        lastPage.value = page
      }
    } catch {
      if (mine === generation) {
        failed.value = true
      }
    } finally {
      if (mine === generation) {
        loading.value = false
      }
    }
  }

  /** Load the same pages again: the project has been synced. */
  async function reload(): Promise<void> {
    if (!key) {
      return
    }
    generation += 1
    const mine = generation
    try {
      const fresh: PostCard[] = []
      let count = total.value
      for (let page = firstPage.value; page <= lastPage.value; page += 1) {
        const answer = await fetchPage(page)
        fresh.push(...answer.posts)
        count = answer.total
      }
      if (mine === generation) {
        posts.value = fresh
        total.value = count
      }
    } catch {
      // What is on screen stays; the next sync or visit tries again.
    }
  }

  /** Fetch one post again: one of its files has been downloaded. */
  async function refresh(postId: number): Promise<void> {
    const index = posts.value.findIndex((post) => post.id === postId)
    if (index === -1) {
      return
    }
    const mine = generation
    try {
      const fresh = await api.get<PostDetails>(`/posts/${postId}`)
      if (mine !== generation) {
        return
      }
      const current = posts.value[index]
      // Feeds without texts don't carry them; keep it that way.
      const card: PostCard = current.html === null ? { ...fresh, html: null, media: [] } : fresh
      posts.value = posts.value.map((post) => (post.id === postId ? card : post))
    } catch {
      // The post may have gone; the feed stays as it is.
    }
  }

  /** The post in the feed that a media row belongs to, if it is shown with its media. */
  function postOfMedia(mediaId: number): number | null {
    const owner = posts.value.find((post) => post.media.some((item) => item.id === mediaId))
    return owner ? owner.id : null
  }

  function has(postId: number): boolean {
    return posts.value.some((post) => post.id === postId)
  }

  return {
    posts,
    total,
    perPage,
    firstPage,
    lastPage,
    pages,
    loading,
    failed,
    show,
    reload,
    refresh,
    postOfMedia,
    has,
  }
})
