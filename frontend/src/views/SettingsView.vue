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

import type { ThemeMode } from '@/api/types'
import CookieLoginModal from '@/components/CookieLoginModal.vue'
import FfmpegOffer from '@/components/FfmpegOffer.vue'
import ProjectSettingsForm from '@/components/ProjectSettingsForm.vue'
import { useAccountStore } from '@/stores/account'
import { useDownloadsStore } from '@/stores/downloads'
import { useFfmpegStore } from '@/stores/ffmpeg'
import { useLibraryStore } from '@/stores/library'
import { useMediaStore } from '@/stores/media'
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
const ffmpeg = useFfmpegStore()
const media = useMediaStore()

const cookieModalOpen = ref(false)
const themes: ThemeMode[] = ['system', 'light', 'dark']

/** Where the builds of ffmpeg for Windows are, for a computer the app can't install one on. */
const FFMPEG_BUILDS = 'https://www.gyan.dev/ffmpeg/builds/'

onMounted(() => {
  void ffmpeg.load().catch(() => undefined)
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

function ffmpegError(code: string): string {
  const key = `ffmpeg.errors.${code}`
  return t(te(key) ? key : 'ffmpeg.errors.unknown')
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

    <Card v-if="ffmpeg.info" size="small" :title="t('settings.ffmpeg.title')">
      <template v-if="ffmpeg.info.found">
        <p class="settings__line">
          {{ t(ffmpeg.info.chosen ? 'settings.ffmpeg.chosen' : 'settings.ffmpeg.found') }}
        </p>
        <code class="settings__path">{{ ffmpeg.info.path }}</code>
        <p v-if="ffmpeg.info.version" class="settings__hint">
          {{ t('settings.ffmpeg.version', { version: ffmpeg.info.version }) }}
        </p>
      </template>
      <template v-else>
        <Alert
          type="warning"
          show-icon
          :message="t('ffmpeg.missing')"
          :description="t('ffmpeg.missingHint')"
        />
        <p v-if="ffmpeg.info.can_install" class="settings__line settings__line--spaced">
          {{ t('settings.ffmpeg.canInstall') }}
        </p>
        <p v-else class="settings__line settings__line--spaced">
          {{ t(`settings.ffmpeg.hints.${ffmpeg.info.platform}`) }}
        </p>
      </template>

      <div class="settings__row settings__row--spaced">
        <FfmpegOffer v-if="ffmpeg.info.can_install" type="primary" />
        <Button
          v-else-if="!ffmpeg.info.found && ffmpeg.info.platform === 'windows'"
          @click="media.openLink(FFMPEG_BUILDS)"
        >
          {{ t('settings.ffmpeg.builds') }}
        </Button>
        <Button :disabled="ffmpeg.busy || ffmpeg.info.installing" @click="ffmpeg.choose()">
          {{ t('settings.ffmpeg.choose') }}
        </Button>
        <Button v-if="ffmpeg.info.chosen" :disabled="ffmpeg.busy" @click="ffmpeg.forget()">
          {{ t('settings.ffmpeg.forget') }}
        </Button>
        <Button
          v-if="!ffmpeg.info.found"
          :disabled="ffmpeg.busy || ffmpeg.info.installing"
          @click="ffmpeg.check()"
        >
          {{ t('settings.ffmpeg.check') }}
        </Button>
      </div>
      <Alert
        v-if="ffmpeg.failure || ffmpeg.info.error"
        class="settings__alert"
        type="error"
        show-icon
        :message="ffmpegError(ffmpeg.failure ?? ffmpeg.info.error ?? '')"
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

.settings__row--spaced {
  margin-top: 12px;
}

.settings__line {
  margin: 0 0 4px;
}

.settings__line--spaced {
  margin-top: 12px;
}

.settings__alert {
  margin-top: 12px;
}

.settings__hint {
  margin: 8px 0 0;
  font-size: 13px;
  opacity: 0.65;
}
</style>
