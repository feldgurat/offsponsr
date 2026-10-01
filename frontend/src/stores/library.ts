import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api, ApiError } from '@/api/client'
import type { FolderChoice, LibraryFailure, LibraryInfo, LibraryStatus } from '@/api/types'

import { useAccountStore } from './account'

export const useLibraryStore = defineStore('library', () => {
  const current = ref<LibraryInfo | null>(null)
  /** Why the library from the previous run didn't open, until the user picks another. */
  const lastFailure = ref<LibraryFailure | null>(null)
  /** Why the user's latest attempt to create or open a library failed. */
  const actionFailure = ref<LibraryFailure | null>(null)
  const busy = ref(false)

  async function load(): Promise<void> {
    const status = await api.get<LibraryStatus>('/library')
    current.value = status.library
    lastFailure.value = status.last_failure
  }

  /** Ask for a folder with the system dialog, then create or open a library there. */
  async function choose(action: 'create' | 'open'): Promise<void> {
    busy.value = true
    actionFailure.value = null
    let path = ''
    try {
      const choice = await api.post<FolderChoice>('/dialogs/folder')
      if (choice.path === null) {
        return
      }
      path = choice.path
      const opened = await api.post<LibraryInfo>(`/library/${action}`, { path })
      // Each library has its own account; find out who is signed in before showing it.
      await useAccountStore()
        .load()
        .catch(() => undefined)
      current.value = opened
      lastFailure.value = null
    } catch (error) {
      const code = error instanceof ApiError ? error.code : null
      actionFailure.value = { path, code: code ?? 'unknown' }
    } finally {
      busy.value = false
    }
  }

  return {
    current,
    lastFailure,
    actionFailure,
    busy,
    load,
    create: () => choose('create'),
    open: () => choose('open'),
  }
})
