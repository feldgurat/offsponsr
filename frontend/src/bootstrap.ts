import { createPinia } from 'pinia'
import { createApp, type App } from 'vue'

import { openSession } from './api/session'
import AppRoot from './App.vue'
import { i18n } from './i18n'
import { createAppRouter } from './router'

export async function createOffsponsrApp(): Promise<App> {
  try {
    await openSession()
  } catch {
    // The app shell reports the lost backend once its first API call fails.
  }

  return createApp(AppRoot).use(createPinia()).use(createAppRouter()).use(i18n)
}
