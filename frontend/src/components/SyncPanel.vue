<script setup lang="ts">
import { Alert, Button, Card, Progress } from 'ant-design-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useSyncStore } from '@/stores/sync'

const { t, te } = useI18n()
const sync = useSyncStore()

const running = computed(() => sync.state.running)

const percent = computed(() => {
  const job = running.value
  if (!job || !job.posts_total) {
    return 0
  }
  return Math.min(100, Math.round((job.posts_done / job.posts_total) * 100))
})

function reason(code: string): string {
  const key = `sync.errors.${code}`
  return t(te(key) ? key : 'sync.errors.unknown')
}
</script>

<template>
  <div v-if="running || sync.state.failures.length" class="sync-panel">
    <Card v-if="running" size="small" class="sync-panel__job">
      <div class="sync-panel__head">
        <strong>{{ t('sync.running', { title: running.title }) }}</strong>
        <Button size="small" :loading="sync.state.cancelling" @click="sync.cancel()">
          {{ sync.state.cancelling ? t('sync.cancelling') : t('sync.cancel') }}
        </Button>
      </div>
      <Progress :percent="percent" :status="running.posts_total === null ? 'active' : undefined" />
      <div class="sync-panel__details">
        <span v-if="running.posts_total === null">{{ t('sync.preparing') }}</span>
        <span v-else>
          {{ t('sync.progress', { done: running.posts_done, total: running.posts_total }) }}
        </span>
        <span v-if="sync.state.queue.length">
          {{ t('sync.queue', { n: sync.state.queue.length }) }}
        </span>
      </div>
    </Card>

    <Alert
      v-for="failure in sync.state.failures"
      :key="failure.project_id"
      class="sync-panel__failure"
      type="error"
      show-icon
      :message="t('sync.failed', { title: failure.title })"
      :description="reason(failure.code)"
    />
  </div>
</template>

<style scoped>
.sync-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 24px;
}

.sync-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.sync-panel__details {
  display: flex;
  justify-content: space-between;
  opacity: 0.65;
}
</style>
