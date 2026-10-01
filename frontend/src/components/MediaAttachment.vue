<script setup lang="ts">
import { FolderOpenOutlined, PaperClipOutlined } from '@ant-design/icons-vue'
import { Button } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'

import type { MediaInfo } from '@/api/types'
import { useFormat } from '@/composables/format'
import { useMediaStore } from '@/stores/media'

import MediaDownload from './MediaDownload.vue'

/**
 * A file attached to a post. It is never shown inside the app: once downloaded, a document
 * opens in the system's program for it, and anything else is only shown in its folder.
 */
defineProps<{ media: MediaInfo }>()

const { t } = useI18n()
const { bytes } = useFormat()
const actions = useMediaStore()
</script>

<template>
  <div class="media-attachment">
    <PaperClipOutlined class="media-attachment__icon" />
    <span class="media-attachment__title">
      {{ media.title || media.file_name || t('media.attachment') }}
    </span>
    <span v-if="media.size" class="media-attachment__size">{{ bytes(media.size) }}</span>
    <template v-if="media.state === 'done'">
      <Button v-if="media.can_open" size="small" @click="actions.open(media.id)">
        {{ t('media.open') }}
      </Button>
      <Button size="small" @click="actions.reveal(media.id)">
        <template #icon><FolderOpenOutlined /></template>
        {{ t('media.reveal') }}
      </Button>
    </template>
    <MediaDownload v-else :media="media" />
  </div>
</template>

<style scoped>
.media-attachment {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--c-border, rgba(128, 128, 128, 0.25));
}

.media-attachment__icon {
  opacity: 0.65;
}

.media-attachment__title {
  flex: 1;
  min-width: 160px;
  overflow-wrap: anywhere;
}

.media-attachment__size {
  opacity: 0.65;
}
</style>
