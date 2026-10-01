import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { AppInfo } from '@/api/types'

import { useAccountStore } from './account'
import { useLibraryStore } from './library'
import { useSyncStore } from './sync'

export type AppStatus = 'loading' | 'ready' | 'error'

export const useAppStore = defineStore('app', () => {
  const info = ref<AppInfo | null>(null)
  const status = ref<AppStatus>('loading')

  /** Fetch what the shell needs before it can show anything: the app, the library, the account. */
  async function load(): Promise<void> {
    status.value = 'loading'
    try {
      info.value = await api.get<AppInfo>('/app')
      await useLibraryStore().load()
      await useAccountStore().load()
      // From here on the backend pushes its news: sync progress and changes to the projects.
      useSyncStore().connect()
      status.value = 'ready'
    } catch {
      status.value = 'error'
    }
  }

  return { info, status, load }
})
