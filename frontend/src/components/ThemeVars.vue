<script setup lang="ts">
import { theme } from 'ant-design-vue'
import { watchEffect } from 'vue'

import { useThemeStore } from '@/stores/theme'

/**
 * Hands the colours of the current theme to plain CSS as variables, so that the app's own
 * styles follow the light and the dark theme along with the UI kit. Renders nothing.
 */
const { token } = theme.useToken()
const current = useThemeStore()

watchEffect(() => {
  const colors = token.value
  const root = document.documentElement.style
  root.setProperty('--c-primary', colors.colorPrimary)
  root.setProperty('--c-border', colors.colorBorderSecondary)
  root.setProperty('--c-fill', colors.colorFillQuaternary)
  root.setProperty('--c-card', colors.colorBgContainer)
  root.setProperty('--c-error', colors.colorError)
  // Scrollbars and the built-in audio and video controls follow the theme too.
  root.setProperty('color-scheme', current.isDark ? 'dark' : 'light')
})
</script>

<template>
  <span hidden />
</template>
