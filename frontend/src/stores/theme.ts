import { theme as antTheme } from 'ant-design-vue'
import type { ThemeConfig } from 'ant-design-vue/es/config-provider/context'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type { ThemeMode } from '@/api/types'

import { useSettingsStore } from './settings'

const ACCENT_LIGHT = '#fa541c'
const ACCENT_DARK = '#d84a1b'
// The page behind the cards and the cards themselves in the dark theme.
const DARK_PAGE = '#141414'
const DARK_CARD = '#1d1d1d'

export const useThemeStore = defineStore('theme', () => {
  const settings = useSettingsStore()

  const mode = computed<ThemeMode>({
    get: () => settings.values.theme,
    set: (value) => void settings.change({ theme: value }),
  })

  const systemQuery = window.matchMedia('(prefers-color-scheme: dark)')
  const systemDark = ref(systemQuery.matches)
  systemQuery.addEventListener('change', (event) => {
    systemDark.value = event.matches
  })

  const isDark = computed(() =>
    mode.value === 'system' ? systemDark.value : mode.value === 'dark',
  )

  const antConfig = computed<ThemeConfig>(() => ({
    algorithm: isDark.value ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
    token: {
      colorPrimary: isDark.value ? ACCENT_DARK : ACCENT_LIGHT,
      colorLink: isDark.value ? ACCENT_DARK : ACCENT_LIGHT,
      ...(isDark.value ? { colorBgLayout: DARK_PAGE, colorBgContainer: DARK_CARD } : {}),
    },
  }))

  return { mode, isDark, antConfig }
})
