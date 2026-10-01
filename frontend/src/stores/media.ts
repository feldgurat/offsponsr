import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'

/** What the user can do with a post's files and links: all of it is done by the backend. */
export const useMediaStore = defineStore('media', () => {
  /** Files the user has just asked for; they show as queued before the backend says so. */
  const requested = ref(new Set<number>())

  /** Download one file, whatever its project's settings say. */
  async function download(mediaId: number): Promise<void> {
    requested.value = new Set(requested.value).add(mediaId)
    try {
      await api.post(`/media/${mediaId}/download`)
    } catch {
      forget(mediaId)
    }
  }

  /** The file is through, one way or another: from here on its row tells its state. */
  function forget(mediaId: number): void {
    if (requested.value.has(mediaId)) {
      const rest = new Set(requested.value)
      rest.delete(mediaId)
      requested.value = rest
    }
  }

  /** Open a downloaded document with the system's program for it. */
  async function open(mediaId: number): Promise<void> {
    await api.post(`/media/${mediaId}/open`)
  }

  /** Show a downloaded file in the system's file manager. */
  async function reveal(mediaId: number): Promise<void> {
    await api.post(`/media/${mediaId}/reveal`)
  }

  /** Open a link in the user's browser: the app's window is not a browser. */
  async function openLink(url: string): Promise<void> {
    await api.post('/open-link', { url })
  }

  return { requested, download, forget, open, reveal, openLink }
})
