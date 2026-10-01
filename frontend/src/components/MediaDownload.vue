<script setup lang="ts">
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { Button, Progress } from 'ant-design-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { MediaInfo } from '@/api/types'
import { useFormat } from '@/composables/format'
import { useDownloadsStore } from '@/stores/downloads'
import { useMediaStore } from '@/stores/media'

/** The control for a file that isn't in the library yet: download it, see it coming, try again. */
const props = defineProps<{ media: MediaInfo; label?: string }>()

const { t, te } = useI18n()
const { bytes } = useFormat()
const downloads = useDownloadsStore()
const actions = useMediaStore()

const active = computed(() =>
  downloads.state.active.find((download) => download.key === `media-${props.media.id}`),
)

/** What to show: the row's state, or "queued" right after the user's click. */
const state = computed(() => {
  if (active.value) {
    return 'downloading'
  }
  const waiting = props.media.state === 'pending' || props.media.state === 'error'
  return waiting && actions.requested.has(props.media.id) ? 'queued' : props.media.state
})

const percent = computed(() => {
  const download = active.value
  if (!download?.bytes_total) {
    return 0
  }
  return Math.min(100, Math.round((download.bytes_done / download.bytes_total) * 100))
})

const progress = computed(() => {
  const download = active.value
  if (!download) {
    return ''
  }
  if (download.bytes_total === null) {
    return download.bytes_done ? bytes(download.bytes_done) : ''
  }
  return t('downloads.size', {
    done: bytes(download.bytes_done),
    total: bytes(download.bytes_total),
  })
})

const caption = computed(() => {
  const action = props.label ?? t('media.download')
  return props.media.size ? `${action} · ${bytes(props.media.size)}` : action
})

const reason = computed(() => {
  const key = `media.errors.${props.media.error}`
  return t(te(key) ? key : 'media.errors.unknown')
})
</script>

<template>
  <div class="media-download">
    <template v-if="state === 'downloading'">
      <Progress
        class="media-download__bar"
        size="small"
        :percent="percent"
        :show-info="false"
        status="active"
      />
      <span class="media-download__note">{{ progress || t('media.downloading') }}</span>
    </template>
    <span v-else-if="state === 'queued'" class="media-download__note">{{ t('media.queued') }}</span>
    <template v-else-if="state === 'error'">
      <span class="media-download__error">{{ reason }}</span>
      <Button size="small" @click="actions.download(media.id)">
        <template #icon><ReloadOutlined /></template>
        {{ t('media.retry') }}
      </Button>
    </template>
    <Button v-else size="small" @click="actions.download(media.id)">
      <template #icon><DownloadOutlined /></template>
      {{ caption }}
    </Button>
  </div>
</template>

<style scoped>
.media-download {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.media-download__bar {
  width: 160px;
  margin: 0;
}

.media-download__note {
  opacity: 0.65;
}

.media-download__error {
  color: var(--c-error, #cf1322);
}
</style>
