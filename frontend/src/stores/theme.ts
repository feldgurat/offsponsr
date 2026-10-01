import { theme as antTheme } from 'ant-design-vue'
import type { ThemeConfig } from 'ant-design-vue/es/config-provider/context'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const ACCENT_LIGHT = '#fa541c'
const ACCENT_DARK = '#d84a1b'

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>('system')

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
    },
  }))

  return { mode, isDark, antConfig }
})
