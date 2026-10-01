import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { AppInfo } from '@/api/types'

export type AppStatus = 'loading' | 'ready' | 'error'

export const useAppStore = defineStore('app', () => {
  const info = ref<AppInfo | null>(null)
  const status = ref<AppStatus>('loading')

  async function load(): Promise<void> {
    status.value = 'loading'
    try {
      info.value = await api.get<AppInfo>('/app')
      status.value = 'ready'
    } catch {
      status.value = 'error'
    }
  }

  return { info, status, load }
})
