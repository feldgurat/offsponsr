<script setup lang="ts">
import { ExportOutlined } from '@ant-design/icons-vue'
import { Button } from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { absoluteLink, embedAddress } from '@/post/links'
import { useMediaStore } from '@/stores/media'

/**
 * A player of another site inside a post (YouTube and the like). It is never downloaded:
 * online it is shown in a frame, offline or from an unknown site there is only a link.
 */
const props = defineProps<{ src: string }>()

const { t } = useI18n()
const actions = useMediaStore()

const online = ref(navigator.onLine)
const setOnline = () => {
  online.value = navigator.onLine
}
onMounted(() => {
  window.addEventListener('online', setOnline)
  window.addEventListener('offline', setOnline)
})
onBeforeUnmount(() => {
  window.removeEventListener('online', setOnline)
  window.removeEventListener('offline', setOnline)
})

const framed = computed(() => embedAddress(props.src))
const link = computed(() => absoluteLink(props.src))
</script>

<template>
  <div class="embed">
    <!-- The frame gets scripts and its own origin (a player needs both) but can't reach this page. -->
    <iframe
      v-if="framed && online"
      class="embed__frame"
      :src="framed"
      sandbox="allow-scripts allow-same-origin allow-presentation allow-popups"
      referrerpolicy="strict-origin-when-cross-origin"
      allow="fullscreen; encrypted-media; picture-in-picture"
      allowfullscreen
      loading="lazy"
    />
    <div v-else class="embed__stub">
      {{ framed ? t('media.embedOffline') : t('media.embedUnknown') }}
    </div>
    <Button
      v-if="link"
      type="link"
      size="small"
      class="embed__link"
      @click="actions.openLink(link)"
    >
      <template #icon><ExportOutlined /></template>
      {{ t('media.openInBrowser') }}
    </Button>
  </div>
</template>

<style scoped>
.embed {
  margin: 16px 0;
}

.embed__frame {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  border: 0;
  border-radius: 8px;
  background: #000;
}

.embed__stub {
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: 16 / 5;
  padding: 16px;
  border: 1px dashed var(--c-border, rgba(128, 128, 128, 0.4));
  border-radius: 8px;
  background: var(--c-fill, rgba(128, 128, 128, 0.08));
  text-align: center;
  opacity: 0.85;
}

.embed__link {
  padding-left: 0;
}
</style>
