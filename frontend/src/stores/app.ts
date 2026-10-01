import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { AppInfo } from '@/api/types'

import { useLibraryStore } from './library'

export type AppStatus = 'loading' | 'ready' | 'error'

export const useAppStore = defineStore('app', () => {
  const info = ref<AppInfo | null>(null)
  const status = ref<AppStatus>('loading')

  /** Fetch what the shell needs before it can show anything: the app info and the library. */
  async function load(): Promise<void> {
    status.value = 'loading'
    try {
      info.value = await api.get<AppInfo>('/app')
      await useLibraryStore().load()
      status.value = 'ready'
    } catch {
      status.value = 'error'
    }
  }

  return { info, status, load }
})
