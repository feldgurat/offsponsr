import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { ProjectInfo } from '@/api/types'

/** The projects in the open library. */
export const useProjectsStore = defineStore('projects', () => {
  const list = ref<ProjectInfo[]>([])
  const loaded = ref(false)

  async function load(): Promise<void> {
    list.value = await api.get<ProjectInfo[]>('/projects')
    loaded.value = true
  }

  /**
   * Add subscriptions and/or a project by its address; their first sync starts by itself.
   * Throws ApiError with the backend's code if the address is no good or the site is in trouble.
   */
  async function add(subscriptionIds: number[], address: string): Promise<void> {
    await api.post('/projects', {
      subscription_ids: subscriptionIds,
      address: address.trim() || null,
    })
    await load()
  }

  return { list, loaded, load, add }
})
