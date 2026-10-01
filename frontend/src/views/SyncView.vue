<script setup lang="ts">
import { Alert, Button, Card, Empty, Tag } from 'ant-design-vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { api } from '@/api/client'
import type { FailedDownloads, FfmpegInfo, SyncRun } from '@/api/types'
import DownloadsPanel from '@/components/DownloadsPanel.vue'
import SyncPanel from '@/components/SyncPanel.vue'
import { useFormat } from '@/composables/format'
import { useAccountStore } from '@/stores/account'
import { useDownloadsStore } from '@/stores/downloads'
import { useProjectsStore } from '@/stores/projects'
import { useSyncStore } from '@/stores/sync'

const { t, te } = useI18n()
const { dateTime } = useFormat()
const account = useAccountStore()
const projects = useProjectsStore()
const sync = useSyncStore()
const downloads = useDownloadsStore()

const history = ref<SyncRun[]>([])
const failed = ref<FailedDownloads>({ total: 0, items: [] })
const ffmpeg = ref<FfmpegInfo | null>(null)
const retrying = ref(false)

async function load(): Promise<void> {
  const [runs, failures] = await Promise.all([
    api.get<SyncRun[]>('/sync/history'),
    api.get<FailedDownloads>('/downloads/failed'),
  ])
  history.value = runs
  failed.value = failures
}

onMounted(() => {
  void load().catch(() => undefined)
  void api
    .get<FfmpegInfo>('/ffmpeg')
    .then((info) => {
      ffmpeg.value = info
    })
    .catch(() => undefined)
  if (!projects.loaded) {
    void projects.load().catch(() => undefined)
  }
})

// Whenever the work stops, the history and the list of failures have changed.
watch(
  () => sync.busy || downloads.busy,
  (busy) => {
    if (!busy) {
      void load().catch(() => undefined)
    }
  },
)

const queue = computed(() =>
  sync.state.queue.map((id) => ({ id, title: projects.byId(id)?.title ?? String(id) })),
)

const idle = computed(
  () => !sync.busy && !downloads.busy && !sync.state.failures.length && !failed.value.total,
)

async function retry(): Promise<void> {
  retrying.value = true
  try {
    await api.post('/downloads/retry')
    await load()
  } catch {
    // The list stays as it is; the button can be pressed again.
  } finally {
    retrying.value = false
  }
}

function reason(code: string | null): string {
  const key = `media.errors.${code}`
  return t(te(key) ? key : 'media.errors.unknown')
}

function changes(run: SyncRun): string {
  const parts = []
  if (run.posts_new) {
    parts.push(t('syncPage.new', { n: run.posts_new }))
  }
  if (run.posts_changed) {
    parts.push(t('syncPage.changed', { n: run.posts_changed }))
  }
  if (run.posts_deleted) {
    parts.push(t('syncPage.deleted', { n: run.posts_deleted }))
  }
  return parts.length ? parts.join(', ') : t('syncPage.nothingNew')
}

const outcomeColor = { ok: 'success', cancelled: 'default', failed: 'error', unfinished: 'warning' }
</script>

<template>
  <section class="sync-page">
    <div class="sync-page__head">
      <h1 class="sync-page__title">{{ t('syncPage.title') }}</h1>
      <Button
        v-if="account.info.signed_in && projects.list.length"
        type="primary"
        :disabled="sync.busy"
        @click="sync.start()"
      >
        {{ t('library.updateAll') }}
      </Button>
    </div>

    <Alert
      v-if="ffmpeg && !ffmpeg.found"
      type="warning"
      show-icon
      :message="t('syncPage.noFfmpeg')"
      :description="t('syncPage.noFfmpegHint')"
    />

    <SyncPanel />
    <Card v-if="queue.length" size="small" :title="t('syncPage.queue')">
      <ol class="sync-page__queue">
        <li v-for="item in queue" :key="item.id">{{ item.title }}</li>
      </ol>
    </Card>
    <DownloadsPanel :failures="false" />

    <Empty v-if="idle" :description="t('syncPage.idle')" />

    <Card v-if="failed.total" size="small" :title="t('syncPage.failed', { n: failed.total })">
      <template #extra>
        <Button size="small" :loading="retrying" :disabled="downloads.busy" @click="retry">
          {{ t('syncPage.retry') }}
        </Button>
      </template>
      <ul class="sync-page__list">
        <li v-for="item in failed.items" :key="item.media_id" class="sync-page__item">
          <RouterLink :to="{ name: 'post', params: { id: item.post_id } }">
            {{ item.title || item.post_title }}
          </RouterLink>
          <span class="sync-page__note">{{ t(`media.kinds.${item.kind}`) }}</span>
          <span class="sync-page__reason">{{ reason(item.error) }}</span>
        </li>
      </ul>
      <p v-if="failed.total > failed.items.length" class="sync-page__note">
        {{ t('syncPage.more', { n: failed.total - failed.items.length }) }}
      </p>
    </Card>

    <Card v-if="history.length" size="small" :title="t('syncPage.history')">
      <ul class="sync-page__list">
        <li v-for="run in history" :key="run.id" class="sync-page__item">
          <span class="sync-page__when">{{ dateTime(run.started_at) }}</span>
          <RouterLink
            v-if="run.project_id !== null && run.title"
            :to="{ name: 'project', params: { id: run.project_id } }"
          >
            {{ run.title }}
          </RouterLink>
          <span v-else>{{ t('syncPage.removedProject') }}</span>
          <Tag :color="outcomeColor[run.outcome]" :bordered="false">
            {{ t(`syncPage.outcomes.${run.outcome}`) }}
          </Tag>
          <span v-if="run.outcome === 'ok'" class="sync-page__note">{{ changes(run) }}</span>
        </li>
      </ul>
    </Card>
  </section>
</template>

<style scoped>
.sync-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* The panels bring their own bottom margin for the pages that have nothing under them. */
.sync-page :deep(.sync-panel),
.sync-page :deep(.downloads-panel) {
  margin-bottom: 0;
}

.sync-page__head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sync-page__title {
  flex: 1;
  margin: 0;
  font-size: 30px;
  font-weight: 500;
}

.sync-page__queue {
  margin: 0;
  padding-left: 1.5em;
}

.sync-page__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.sync-page__item {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
  padding: 6px 0;
}

.sync-page__when,
.sync-page__note {
  opacity: 0.65;
}

.sync-page__reason {
  color: var(--c-error, #cf1322);
}
</style>
