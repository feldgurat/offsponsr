<script setup lang="ts">
import {
  Alert,
  Button,
  Card,
  Collapse,
  CollapsePanel,
  RadioButton,
  RadioGroup,
} from 'ant-design-vue'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/client'
import type { FfmpegInfo, ThemeMode } from '@/api/types'
import CookieLoginModal from '@/components/CookieLoginModal.vue'
import ProjectSettingsForm from '@/components/ProjectSettingsForm.vue'
import { useAccountStore } from '@/stores/account'
import { useDownloadsStore } from '@/stores/downloads'
import { useLibraryStore } from '@/stores/library'
import { useProjectsStore } from '@/stores/projects'
import { useSyncStore } from '@/stores/sync'
import { useThemeStore } from '@/stores/theme'

const { t, te } = useI18n()
const theme = useThemeStore()
const library = useLibraryStore()
const account = useAccountStore()
const projects = useProjectsStore()
const sync = useSyncStore()
const downloads = useDownloadsStore()

const ffmpeg = ref<FfmpegInfo | null>(null)
const cookieModalOpen = ref(false)
const themes: ThemeMode[] = ['system', 'light', 'dark']

onMounted(() => {
  void api
    .get<FfmpegInfo>('/ffmpeg')
    .then((info) => {
      ffmpeg.value = info
    })
    .catch(() => undefined)
  if (!projects.loaded) {
    void projects.load().catch(() => undefined)
  }
})

/** Another library means other projects: the list on hand is not theirs. */
async function switchLibrary(action: 'create' | 'open'): Promise<void> {
  const before = library.current?.id
  await library[action]()
  if (library.current?.id !== before) {
    await projects.load().catch(() => undefined)
  }
}

function libraryError(code: string): string {
  // `sync_running` comes from the backend when something is still being written into the library.
  const key = code === 'sync_running' ? 'settings.library.busy' : `libraryError.${code}`
  return t(te(key) ? key : 'libraryError.unknown')
}
</script>

<template>
  <section class="settings">
    <h1 class="settings__title">{{ t('settings.title') }}</h1>

    <Card size="small" :title="t('settings.theme.title')">
      <RadioGroup
        :value="theme.mode"
        button-style="solid"
        @change="(event) => (theme.mode = event.target.value)"
      >
        <RadioButton v-for="mode in themes" :key="mode" :value="mode">
          {{ t(`settings.theme.${mode}`) }}
        </RadioButton>
      </RadioGroup>
    </Card>

    <Card size="small" :title="t('settings.account.title')">
      <div class="settings__row">
        <template v-if="account.info.signed_in">
          <span class="settings__grow">
            {{ t('settings.account.signedIn', { email: account.info.email }) }}
          </span>
          <Button :disabled="account.busy" @click="account.logout()">
            {{ t('account.signOut') }}
          </Button>
        </template>
        <template v-else>
          <span class="settings__grow">{{ t('settings.account.signedOut') }}</span>
          <Button @click="cookieModalOpen = true">{{ t('account.withCookie') }}</Button>
          <Button type="primary" :loading="account.busy" @click="account.login()">
            {{ t('account.signIn') }}
          </Button>
        </template>
      </div>
      <p class="settings__hint">{{ t('settings.account.hint') }}</p>
    </Card>

    <Card size="small" :title="t('settings.library.title')">
      <div class="settings__row">
        <code class="settings__grow settings__path">{{ library.current?.path }}</code>
        <Button
          :disabled="library.busy || sync.busy || downloads.busy"
          @click="switchLibrary('open')"
        >
          {{ t('settings.library.open') }}
        </Button>
        <Button
          :disabled="library.busy || sync.busy || downloads.busy"
          @click="switchLibrary('create')"
        >
          {{ t('settings.library.create') }}
        </Button>
      </div>
      <p class="settings__hint">{{ t('settings.library.hint') }}</p>
      <Alert
        v-if="library.actionFailure"
        type="error"
        show-icon
        :message="libraryError(library.actionFailure.code)"
        :description="library.actionFailure.path"
      />
    </Card>

    <Card size="small" :title="t('settings.ffmpeg.title')">
      <template v-if="ffmpeg?.found">
        <p class="settings__line">{{ t('settings.ffmpeg.found') }}</p>
        <code class="settings__path">{{ ffmpeg.path }}</code>
      </template>
      <Alert
        v-else-if="ffmpeg"
        type="warning"
        show-icon
        :message="t('syncPage.noFfmpeg')"
        :description="t('syncPage.noFfmpegHint')"
      />
    </Card>

    <Card size="small" :title="t('settings.projects.title')">
      <p v-if="!projects.list.length" class="settings__hint">{{ t('library.empty') }}</p>
      <Collapse v-else accordion ghost>
        <CollapsePanel v-for="project in projects.list" :key="project.id" :header="project.title">
          <ProjectSettingsForm :project="project" />
        </CollapsePanel>
      </Collapse>
    </Card>

    <CookieLoginModal v-model:open="cookieModalOpen" />
  </section>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.settings__title {
  margin: 0;
  font-size: 30px;
  font-weight: 500;
}

.settings__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.settings__grow {
  flex: 1;
  min-width: 200px;
}

.settings__path {
  overflow-wrap: anywhere;
}

.settings__line {
  margin: 0 0 4px;
}

.settings__hint {
  margin: 8px 0 0;
  font-size: 13px;
  opacity: 0.65;
}
</style>
