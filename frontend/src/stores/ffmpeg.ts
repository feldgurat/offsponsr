import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api, ApiError } from '@/api/client'
import type { FfmpegInfo } from '@/api/types'

/** ffmpeg: whether the computer has one, installing one, pointing at one. */
export const useFfmpegStore = defineStore('ffmpeg', () => {
  /** null until asked for; the backend's events keep it current afterwards. */
  const info = ref<FfmpegInfo | null>(null)
  const busy = ref(false)
  /** The code of why the last request was refused. */
  const failure = ref<string | null>(null)
  let asked: Promise<void> | null = null

  async function load(): Promise<void> {
    info.value = await api.get<FfmpegInfo>('/ffmpeg')
  }

  /** Ask once: for the places that only show what the events keep up to date. */
  function ensure(): Promise<void> {
    asked ??= load().catch(() => {
      asked = null
    })
    return asked
  }

  async function act(request: () => Promise<FfmpegInfo>): Promise<void> {
    busy.value = true
    failure.value = null
    try {
      info.value = await request()
    } catch (error) {
      failure.value = (error instanceof ApiError && error.code) || 'unknown'
    } finally {
      busy.value = false
    }
  }

  /** Have winget install ffmpeg; the events tell when it is through. */
  function install(): Promise<void> {
    return act(() => api.post<FfmpegInfo>('/ffmpeg/install'))
  }

  /** Let the user point at their ffmpeg in the system's file dialog. */
  function choose(): Promise<void> {
    return act(() => api.post<FfmpegInfo>('/ffmpeg/choose'))
  }

  /** Go back to the ffmpeg the app finds by itself. */
  function forget(): Promise<void> {
    return act(() => api.delete<FfmpegInfo>('/ffmpeg/choice'))
  }

  /** Look again: the user may have installed ffmpeg by their own means. */
  function check(): Promise<void> {
    return act(() => api.post<FfmpegInfo>('/ffmpeg/check'))
  }

  return { info, busy, failure, load, ensure, install, choose, forget, check }
})
