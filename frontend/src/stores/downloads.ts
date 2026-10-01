import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import type { DownloadsInfo } from '@/api/types'

const IDLE: DownloadsInfo = { active: [], queued: 0, done: 0, failed: 0, cancelling: false }

/** The background downloads of media. The state arrives over the event stream (see the sync store). */
export const useDownloadsStore = defineStore('downloads', () => {
  const state = ref<DownloadsInfo>(IDLE)

  const busy = computed(() => state.value.active.length > 0 || state.value.queued > 0)
  /** Everything in the current batch: finished, failed, in flight and waiting. */
  const total = computed(
    () => state.value.done + state.value.failed + state.value.active.length + state.value.queued,
  )

  async function cancel(): Promise<void> {
    state.value = await api.post<DownloadsInfo>('/downloads/cancel')
  }

  return { state, busy, total, cancel }
})
