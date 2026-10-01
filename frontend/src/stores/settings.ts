import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { Settings } from '@/api/types'

const DEFAULTS: Settings = { theme: 'system', feed_view: 'stream', hide_closed: false }

/**
 * The user's settings for the interface. The backend keeps them: the window's own storage
 * doesn't outlive the app, which gets a new address on every start.
 */
export const useSettingsStore = defineStore('settings', () => {
  const values = ref<Settings>({ ...DEFAULTS })

  async function load(): Promise<void> {
    values.value = await api.get<Settings>('/settings')
  }

  /** Apply the change at once and save it; a failed save leaves the change in place for this run. */
  async function change(changes: Partial<Settings>): Promise<void> {
    values.value = { ...values.value, ...changes }
    try {
      values.value = { ...(await api.patch<Settings>('/settings', changes)), ...changes }
    } catch {
      // Not being able to save a preference is no reason to interrupt the user.
    }
  }

  return { values, load, change }
})
