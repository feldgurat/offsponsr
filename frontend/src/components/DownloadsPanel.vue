<script setup lang="ts">
import { Alert, Button, Card, Progress } from 'ant-design-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ActiveDownload } from '@/api/types'
import { useDownloadsStore } from '@/stores/downloads'

const { t } = useI18n()
const downloads = useDownloadsStore()

const finished = computed(() => downloads.state.done + downloads.state.failed)
const percent = computed(() =>
  downloads.total ? Math.round((finished.value / downloads.total) * 100) : 0,
)

/** 1536 -> «1,5 КБ». */
function formatBytes(bytes: number): string {
  const units = ['b', 'kb', 'mb', 'gb'].map((unit) => t(`downloads.units.${unit}`))
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  const digits = unit === 0 || value >= 100 ? 0 : 1
  return `${value.toLocaleString('ru', { maximumFractionDigits: digits })} ${units[unit]}`
}

function size(download: ActiveDownload): string {
  if (download.bytes_total === null) {
    return download.bytes_done ? formatBytes(download.bytes_done) : ''
  }
  return t('downloads.size', {
    done: formatBytes(download.bytes_done),
    total: formatBytes(download.bytes_total),
  })
}
</script>

<template>
  <div v-if="downloads.busy || downloads.state.failed" class="downloads-panel">
    <Card v-if="downloads.busy" size="small">
      <div class="downloads-panel__head">
        <strong>{{ t('downloads.title') }}</strong>
        <Button size="small" :loading="downloads.state.cancelling" @click="downloads.cancel()">
          {{ downloads.state.cancelling ? t('downloads.cancelling') : t('downloads.cancel') }}
        </Button>
      </div>
      <Progress :percent="percent" />
      <div class="downloads-panel__details">
        {{ t('downloads.progress', { done: finished, total: downloads.total }, downloads.total) }}
      </div>
      <ul class="downloads-panel__active">
        <li v-for="download in downloads.state.active" :key="download.key">
          <span class="downloads-panel__name">{{ download.title }}</span>
          <span>{{ size(download) }}</span>
        </li>
      </ul>
    </Card>

    <Alert
      v-if="downloads.state.failed"
      type="warning"
      show-icon
      :message="t('downloads.failed', { n: downloads.state.failed })"
      :description="t('downloads.failedHint')"
    />
  </div>
</template>

<style scoped>
.downloads-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 24px;
}

.downloads-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.downloads-panel__details {
  opacity: 0.65;
}

.downloads-panel__active {
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
  opacity: 0.85;
}

.downloads-panel__active li {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.downloads-panel__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
