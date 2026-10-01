import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api, ApiError } from '@/api/client'
import type { AccountInfo } from '@/api/types'

const SIGNED_OUT: AccountInfo = { signed_in: false, email: null, expired: false }

/** The sponsr.ru account of the open library. */
export const useAccountStore = defineStore('account', () => {
  const info = ref<AccountInfo>(SIGNED_OUT)
  /** A sign-in or sign-out is under way; with the login window it can take minutes. */
  const busy = ref(false)
  /** The error code of the latest failed attempt. */
  const failure = ref<string | null>(null)

  async function load(): Promise<void> {
    info.value = await api.get<AccountInfo>('/account')
  }

  /** Returns whether the request went through (which, for a login, may still mean "cancelled"). */
  async function run(request: () => Promise<AccountInfo>): Promise<boolean> {
    busy.value = true
    failure.value = null
    try {
      info.value = await request()
      return true
    } catch (error) {
      failure.value = (error instanceof ApiError ? error.code : null) ?? 'unknown'
      return false
    } finally {
      busy.value = false
    }
  }

  return {
    info,
    busy,
    failure,
    load,
    /** Opens the sponsr.ru login window and waits for it to close. */
    login: () => run(() => api.post<AccountInfo>('/account/login')),
    loginWithCookie: (cookie: string) =>
      run(() => api.post<AccountInfo>('/account/login/cookie', { cookie })),
    logout: () => run(() => api.post<AccountInfo>('/account/logout')),
    dismissFailure: () => {
      failure.value = null
    },
  }
})
