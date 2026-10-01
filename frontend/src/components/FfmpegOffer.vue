<script setup lang="ts">
import { LoadingOutlined } from '@ant-design/icons-vue'
import { Button, Modal } from 'ant-design-vue'
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useFfmpegStore } from '@/stores/ffmpeg'

/**
 * What to do about a missing ffmpeg, in one control: install it, see it being installed,
 * or go and read how to get one. Shows nothing while there is an ffmpeg.
 */
defineProps<{ size?: 'small' | 'middle'; type?: 'default' | 'primary' }>()

const { t } = useI18n()
const ffmpeg = useFfmpegStore()

onMounted(() => {
  void ffmpeg.ensure()
})

/** Installing downloads a program and puts it into the system: not without a yes. */
function offer(): void {
  Modal.confirm({
    title: t('ffmpeg.confirm.title'),
    content: t('ffmpeg.confirm.text'),
    okText: t('ffmpeg.confirm.ok'),
    cancelText: t('ffmpeg.confirm.cancel'),
    onOk: () => ffmpeg.install(),
  })
}
</script>

<template>
  <template v-if="ffmpeg.info && !ffmpeg.info.found">
    <span v-if="ffmpeg.info.installing" class="ffmpeg-offer__note">
      <LoadingOutlined />
      {{ t('ffmpeg.installing') }}
    </span>
    <Button
      v-else-if="ffmpeg.info.can_install"
      :size="size"
      :type="type"
      :loading="ffmpeg.busy"
      @click="offer"
    >
      {{ t('ffmpeg.install') }}
    </Button>
    <RouterLink v-else :to="{ name: 'settings' }">{{ t('ffmpeg.howTo') }}</RouterLink>
  </template>
</template>

<style scoped>
.ffmpeg-offer__note {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  opacity: 0.85;
}
</style>
