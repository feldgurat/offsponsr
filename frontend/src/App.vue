<script setup lang="ts">
import {
  ConfigProvider,
  Layout,
  LayoutContent,
  LayoutFooter,
  LayoutHeader,
  Result,
  Spin,
} from 'ant-design-vue'
import ruRU from 'ant-design-vue/es/locale/ru_RU'
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, RouterView } from 'vue-router'

import AccountMenu from '@/components/AccountMenu.vue'
import AccountNotice from '@/components/AccountNotice.vue'
import { useAppStore } from '@/stores/app'
import { useLibraryStore } from '@/stores/library'
import { useThemeStore } from '@/stores/theme'
import WelcomeView from '@/views/WelcomeView.vue'

const { t } = useI18n()
const app = useAppStore()
const library = useLibraryStore()
const theme = useThemeStore()

onMounted(() => app.load())
</script>

<template>
  <ConfigProvider :locale="ruRU" :theme="theme.antConfig">
    <Layout class="app">
      <LayoutHeader v-if="library.current" class="app__header">
        <RouterLink class="app__brand" :to="{ name: 'library' }">{{ t('app.title') }}</RouterLink>
        <AccountMenu />
      </LayoutHeader>

      <LayoutContent class="app__content">
        <Result
          v-if="app.status === 'error'"
          status="error"
          :title="t('app.backendError.title')"
          :sub-title="t('app.backendError.hint')"
        />
        <Spin v-else-if="app.status === 'loading'" class="app__spin" :tip="t('app.loading')" />
        <!-- Nothing in the app works without a library, so there is nowhere else to go yet. -->
        <WelcomeView v-else-if="!library.current" />
        <template v-else>
          <AccountNotice />
          <RouterView />
        </template>
      </LayoutContent>

      <LayoutFooter v-if="app.info" class="app__footer">
        {{ t('app.version', { version: app.info.version }) }}
      </LayoutFooter>
    </Layout>
  </ConfigProvider>
</template>

<style scoped>
.app {
  min-height: 100vh;
}

.app__header {
  display: flex;
  align-items: center;
}

.app__brand {
  color: #fff;
  font-size: 18px;
  font-weight: 500;
}

.app__content {
  width: 100%;
  max-width: 920px;
  margin: 0 auto;
  padding: 24px 16px;
}

.app__spin {
  display: block;
  margin: 64px auto;
}

.app__footer {
  text-align: center;
  opacity: 0.65;
}
</style>
