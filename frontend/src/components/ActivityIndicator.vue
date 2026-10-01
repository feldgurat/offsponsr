<script setup lang="ts">
import { SyncOutlined } from '@ant-design/icons-vue'
import { Badge } from 'ant-design-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useDownloadsStore } from '@/stores/downloads'
import { useSyncStore } from '@/stores/sync'

/**
 * The header's link to the sync page. It tells, on any page, that projects are being updated
 * or files downloaded, and that something failed.
 */
const { t } = useI18n()
const sync = useSyncStore()
const downloads = useDownloadsStore()

const busy = computed(() => sync.busy || downloads.busy)
const failures = computed(() => sync.state.failures.length + downloads.state.failed)

const label = computed(() => {
  if (sync.state.running) {
    return t('activity.syncing', { title: sync.state.running.title })
  }
  if (downloads.busy) {
    const left = downloads.state.active.length + downloads.state.queued
    return t('activity.downloading', { n: left }, left)
  }
  return t('activity.idle')
})
</script>

<template>
  <RouterLink :to="{ name: 'sync' }" class="activity" :class="{ 'activity--busy': busy }">
    <Badge v-if="failures && !busy" :count="failures" size="small" :offset="[2, -2]">
      <SyncOutlined class="activity__icon" />
    </Badge>
    <SyncOutlined v-else class="activity__icon" :spin="busy" />
    <span class="activity__label">{{ label }}</span>
  </RouterLink>
</template>

<style scoped>
.activity {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: rgba(255, 255, 255, 0.65);
}

.activity:hover,
.activity--busy,
.activity.router-link-active {
  color: #fff;
}

/* The badge brings the page's text colour with it; the icon goes by the header's. */
.activity :deep(.ant-badge) {
  color: inherit;
}

.activity__icon {
  font-size: 16px;
}

.activity__label {
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
