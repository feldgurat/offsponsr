import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import type { ServerEvent, SyncInfo } from '@/api/types'

import { useAccountStore } from './account'
import { useDownloadsStore } from './downloads'
import { useProjectsStore } from './projects'

const IDLE: SyncInfo = { running: null, queue: [], failures: [], cancelling: false }

export type ProjectSyncStatus = 'running' | 'queued' | 'idle'

/** The background sync: what is being downloaded, what waits, what failed. */
export const useSyncStore = defineStore('sync', () => {
  const state = ref<SyncInfo>(IDLE)
  let source: EventSource | null = null

  const busy = computed(() => state.value.running !== null || state.value.queue.length > 0)

  function statusOf(projectId: number): ProjectSyncStatus {
    if (state.value.running?.project_id === projectId) {
      return 'running'
    }
    return state.value.queue.includes(projectId) ? 'queued' : 'idle'
  }

  function apply(next: SyncInfo): void {
    const wasBusy = busy.value
    state.value = next
    if (wasBusy && !busy.value) {
      // A sync that hit an expired session signs the account out; show that without a reload.
      void useAccountStore()
        .load()
        .catch(() => undefined)
    }
  }

  function handle(event: ServerEvent): void {
    if (event.type === 'sync') {
      apply(event.state)
    } else if (event.type === 'downloads') {
      useDownloadsStore().state = event.state
    } else if (event.type === 'projects') {
      void useProjectsStore()
        .load()
        .catch(() => undefined)
    }
  }

  /** Start listening to the backend's events. The browser reconnects by itself if the stream drops. */
  function connect(): void {
    if (source !== null || typeof EventSource === 'undefined') {
      return
    }
    source = new EventSource('/api/events')
    source.onmessage = (message: MessageEvent<string>) => {
      handle(JSON.parse(message.data) as ServerEvent)
    }
  }

  function disconnect(): void {
    source?.close()
    source = null
  }

  /** Update the given projects, or every project when called without ids. */
  async function start(projectIds?: number[]): Promise<void> {
    apply(await api.post<SyncInfo>('/sync', { project_ids: projectIds ?? null }))
  }

  async function cancel(): Promise<void> {
    apply(await api.post<SyncInfo>('/sync/cancel'))
  }

  return { state, busy, statusOf, connect, disconnect, handle, start, cancel }
})
