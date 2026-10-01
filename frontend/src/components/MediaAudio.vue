<script setup lang="ts">
import { FolderOpenOutlined, SoundOutlined } from '@ant-design/icons-vue'
import { Button, Tooltip } from 'ant-design-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { MediaInfo } from '@/api/types'
import { useFormat } from '@/composables/format'
import { useMediaStore } from '@/stores/media'

import MediaDownload from './MediaDownload.vue'

/** A post's audio file: its name, how long it is, and the player or the way to download it. */
const props = defineProps<{ media: MediaInfo }>()

const { t } = useI18n()
const { bytes, clock } = useFormat()
const actions = useMediaStore()

const details = computed(() => {
  const parts = []
  if (props.media.duration) {
    parts.push(clock(props.media.duration))
  }
  if (props.media.size) {
    parts.push(bytes(props.media.size))
  }
  return parts.join(' · ')
})
</script>

<template>
  <div class="media-audio">
    <div class="media-audio__head">
      <SoundOutlined class="media-audio__icon" />
      <span class="media-audio__title">{{ media.title || t('media.audio') }}</span>
      <span v-if="details" class="media-audio__details">{{ details }}</span>
      <Tooltip v-if="media.url" :title="t('media.reveal')">
        <Button
          type="text"
          size="small"
          :aria-label="t('media.reveal')"
          @click="actions.reveal(media.id)"
        >
          <template #icon><FolderOpenOutlined /></template>
        </Button>
      </Tooltip>
    </div>
    <audio v-if="media.url" class="media-audio__player" controls preload="none" :src="media.url" />
    <MediaDownload v-else :media="media" />
  </div>
</template>

<style scoped>
.media-audio {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 12px 0;
  padding: 12px 16px;
  border: 1px solid var(--c-border, rgba(128, 128, 128, 0.25));
  border-radius: 8px;
}

.media-audio__head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.media-audio__icon {
  opacity: 0.65;
}

.media-audio__title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.media-audio__details {
  flex-shrink: 0;
  opacity: 0.65;
}

.media-audio__player {
  width: 100%;
  height: 40px;
}
</style>
