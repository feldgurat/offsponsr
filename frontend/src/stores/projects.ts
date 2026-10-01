import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { PendingMedia, ProjectInfo, ProjectSettings, ProjectUpdate } from '@/api/types'

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

  function byId(id: number): ProjectInfo | undefined {
    return list.value.find((project) => project.id === id)
  }

  /**
   * Change a project's settings. Returns what there now is to download, for the kinds of media
   * just switched to «сразу»: the caller asks the user before downloading it.
   */
  async function change(id: number, settings: ProjectSettings): Promise<PendingMedia> {
    const update = await api.patch<ProjectUpdate>(`/projects/${id}`, settings)
    list.value = list.value.map((project) => (project.id === id ? update.project : project))
    return update.to_download
  }

  /** Queue what the project is missing on disk, by its settings. */
  async function download(id: number): Promise<void> {
    await api.post(`/projects/${id}/download`)
  }

  return { list, loaded, load, add, byId, change, download }
})
