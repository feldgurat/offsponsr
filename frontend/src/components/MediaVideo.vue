<script setup lang="ts">
import { FolderOpenOutlined, PlayCircleOutlined } from '@ant-design/icons-vue'
import { Button } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'

import type { MediaInfo } from '@/api/types'
import { useMediaStore } from '@/stores/media'

import MediaDownload from './MediaDownload.vue'

/** A post's video: the player once the file is in the library, the way to get it until then. */
defineProps<{ media: MediaInfo }>()

const { t } = useI18n()
const actions = useMediaStore()
</script>

<template>
  <div class="media-video">
    <template v-if="media.url">
      <video class="media-video__player" controls preload="metadata" :src="media.url" />
      <Button
        type="link"
        size="small"
        class="media-video__reveal"
        @click="actions.reveal(media.id)"
      >
        <template #icon><FolderOpenOutlined /></template>
        {{ t('media.reveal') }}
      </Button>
    </template>
    <div v-else class="media-video__missing">
      <PlayCircleOutlined class="media-video__icon" />
      <div>{{ t('media.videoMissing') }}</div>
      <MediaDownload :media="media" :label="t('media.downloadVideo')" />
    </div>
  </div>
</template>

<style scoped>
.media-video {
  margin: 16px 0;
}

.media-video__player {
  display: block;
  width: 100%;
  max-height: 80vh;
  background: #000;
  border-radius: 8px;
}

.media-video__missing {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  aspect-ratio: 16 / 9;
  padding: 16px;
  border: 1px dashed var(--c-border, rgba(128, 128, 128, 0.4));
  border-radius: 8px;
  background: var(--c-fill, rgba(128, 128, 128, 0.08));
  text-align: center;
}

.media-video__icon {
  font-size: 40px;
  opacity: 0.45;
}

.media-video__reveal {
  padding-left: 0;
}
</style>
