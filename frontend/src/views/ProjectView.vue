<script setup lang="ts">
import {
  AppstoreOutlined,
  BarsOutlined,
  FilterOutlined,
  ProfileOutlined,
  ReadOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import {
  Alert,
  Button,
  Checkbox,
  Empty,
  Modal,
  Pagination,
  RadioButton,
  RadioGroup,
  RangePicker,
  Result,
  Select,
  Spin,
  Tag,
} from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { type LocationQueryRaw, RouterLink, useRoute, useRouter } from 'vue-router'

import type { FeedView } from '@/api/types'
import FeedPost from '@/components/FeedPost.vue'
import ProjectSettingsForm from '@/components/ProjectSettingsForm.vue'
import { useFormat } from '@/composables/format'
import { useAccountStore } from '@/stores/account'
import { type FeedFilters, useFeedStore } from '@/stores/feed'
import { useProjectsStore } from '@/stores/projects'
import { useSettingsStore } from '@/stores/settings'
import { type FileEvent, useSyncStore } from '@/stores/sync'

const { t } = useI18n()
const { dateTime } = useFormat()
const route = useRoute()
const router = useRouter()
const account = useAccountStore()
const projects = useProjectsStore()
const settings = useSettingsStore()
const sync = useSyncStore()
const feed = useFeedStore()

const settingsOpen = ref(false)
const toolbar = ref<HTMLElement | null>(null)

const projectId = computed(() => Number(route.params.id))
const project = computed(() => projects.byId(projectId.value))

const views: { value: FeedView; icon: typeof BarsOutlined }[] = [
  { value: 'stream', icon: ReadOutlined },
  { value: 'feed', icon: ProfileOutlined },
  { value: 'tile', icon: AppstoreOutlined },
  { value: 'list', icon: BarsOutlined },
]
const view = computed(() => settings.values.feed_view)

function text(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null
}

function pageNumber(value: unknown): number | null {
  const number = Number(text(value))
  return Number.isInteger(number) && number >= 1 ? number : null
}

const DAY = /^\d{4}-\d{2}-\d{2}$/

// The page and the filters live in the address, so that going back from a post lands on
// the same place; the view and «скрыть закрытые» are the user's settings and outlive the app.
const filters = computed<FeedFilters>(() => {
  const { order, from, to, content, deleted } = route.query
  return {
    order: order === 'asc' ? 'asc' : 'desc',
    from: DAY.test(text(from) ?? '') ? text(from) : null,
    to: DAY.test(text(to) ?? '') ? text(to) : null,
    content: content === 'audio' || content === 'video' ? content : null,
    hideClosed: settings.values.hide_closed,
    hideDeleted: deleted === 'hide',
    withText: view.value === 'stream',
  }
})
const firstPage = computed(() => pageNumber(route.query.page) ?? 1)
const lastPage = computed(() => Math.max(firstPage.value, pageNumber(route.query.upto) ?? 0))

const filtered = computed(() => {
  const { order, from, to, content, hideDeleted } = filters.value
  return order !== 'desc' || from !== null || to !== null || content !== null || hideDeleted
})
const filtersOpen = ref(filtered.value || settings.values.hide_closed)

const period = computed(() => {
  const { from, to } = filters.value
  return from && to ? [from, to] : undefined
})

const orders = computed(() => [
  { value: 'desc', label: t('feed.newestFirst') },
  { value: 'asc', label: t('feed.oldestFirst') },
])
const contents = computed(() => [
  { value: 'any', label: t('feed.anyContent') },
  { value: 'audio', label: t('feed.withAudio') },
  { value: 'video', label: t('feed.withVideo') },
])

/** Change the filters in the address; the feed starts again from its first page. */
function filterBy(changes: LocationQueryRaw): void {
  const query = { ...route.query, ...changes }
  delete query.page
  delete query.upto
  void router.replace({ query })
}

function setPeriod(value: unknown): void {
  const [from, to] = Array.isArray(value) ? (value as string[]) : []
  filterBy({ from: from || undefined, to: to || undefined })
}

function showMore(): void {
  void router.replace({ query: { ...route.query, upto: feed.lastPage + 1 } })
}

function goToPage(page: number): void {
  const query: LocationQueryRaw = { ...route.query, page: page > 1 ? page : undefined }
  delete query.upto
  void router.push({ query })
  toolbar.value?.scrollIntoView({ block: 'start' })
}

// Watched as text: the filters are a new object on every look, the same or not.
watch(
  () => JSON.stringify([projectId.value, filters.value, firstPage.value, lastPage.value]),
  () => {
    if (Number.isInteger(projectId.value)) {
      void feed.show(projectId.value, filters.value, firstPage.value, lastPage.value)
    }
  },
  { immediate: true },
)

// A finished sync changes `last_synced_at`: what is on screen may be out of date.
watch(
  () => project.value?.last_synced_at,
  (now, before) => {
    if (before !== undefined && now !== before) {
      void feed.reload()
    }
  },
)

/** A cover or a file of one of the posts on screen has been downloaded: show it. */
function onFile(event: FileEvent): void {
  if (event.kind === 'post_cover' && feed.has(event.id)) {
    void feed.refresh(event.id)
  } else if (event.kind === 'media') {
    const postId = feed.postOfMedia(event.id)
    if (postId !== null) {
      void feed.refresh(postId)
    }
  }
}

let stopListening = () => {}
onMounted(() => {
  stopListening = sync.onFile(onFile)
  if (!projects.loaded) {
    void projects.load().catch(() => undefined)
  }
})
onBeforeUnmount(() => stopListening())

const status = computed(() => sync.statusOf(projectId.value))
</script>

<template>
  <Result v-if="projects.loaded && !project" status="404" :title="t('project.missing')">
    <template #extra>
      <RouterLink :to="{ name: 'library' }">
        <Button type="primary">{{ t('project.toLibrary') }}</Button>
      </RouterLink>
    </template>
  </Result>

  <section v-else-if="project" class="project">
    <img v-if="project.cover" class="project__cover" :src="project.cover" alt="" />
    <div class="project__head">
      <img v-if="project.logo" class="project__logo" :src="project.logo" alt="" />
      <div class="project__names">
        <h1 class="project__title">{{ project.title }}</h1>
        <div class="project__meta">
          <span>{{ t('library.posts', { n: project.posts }, project.posts) }}</span>
          <span v-if="project.posts_closed">
            {{ t('project.closed', { n: project.posts_closed }) }}
          </span>
          <span v-if="project.last_synced_at">
            {{ t('library.syncedAt', { date: dateTime(project.last_synced_at) }) }}
          </span>
        </div>
      </div>
      <Tag v-if="status === 'running'" color="processing">{{ t('library.running') }}</Tag>
      <Tag v-else-if="status === 'queued'">{{ t('library.queued') }}</Tag>
      <Button
        v-else-if="account.info.signed_in"
        :disabled="sync.state.cancelling"
        @click="sync.start([project.id])"
      >
        {{ t('library.update') }}
      </Button>
      <Button :aria-label="t('projectSettings.title')" @click="settingsOpen = true">
        <template #icon><SettingOutlined /></template>
      </Button>
    </div>

    <Alert
      v-if="project.posts_without_text"
      class="project__notice"
      type="info"
      show-icon
      :message="t('project.withoutText', { n: project.posts_without_text })"
    />

    <div ref="toolbar" class="project__toolbar">
      <RadioGroup
        :value="view"
        button-style="solid"
        @change="(event) => settings.change({ feed_view: event.target.value })"
      >
        <RadioButton v-for="option in views" :key="option.value" :value="option.value">
          <component :is="option.icon" /> {{ t(`feed.views.${option.value}`) }}
        </RadioButton>
      </RadioGroup>
      <Button :type="filtersOpen ? 'primary' : 'default'" @click="filtersOpen = !filtersOpen">
        <template #icon><FilterOutlined /></template>
        {{ t('feed.filters') }}
      </Button>
      <span class="project__found">{{ t('feed.found', { n: feed.total }, feed.total) }}</span>
    </div>

    <div v-if="filtersOpen" class="project__filters">
      <Select
        class="project__select"
        :value="filters.order"
        :options="orders"
        @change="(order) => filterBy({ order: order === 'asc' ? 'asc' : undefined })"
      />
      <RangePicker
        :value="period as never"
        value-format="YYYY-MM-DD"
        format="DD.MM.YYYY"
        @change="setPeriod"
      />
      <Select
        class="project__select"
        :value="filters.content ?? 'any'"
        :options="contents"
        @change="(kind) => filterBy({ content: kind === 'any' ? undefined : String(kind) })"
      />
      <Checkbox
        :checked="filters.hideClosed"
        @change="(event) => settings.change({ hide_closed: event.target.checked })"
      >
        {{ t('feed.hideClosed') }}
      </Checkbox>
      <Checkbox
        :checked="filters.hideDeleted"
        @change="(event) => filterBy({ deleted: event.target.checked ? 'hide' : undefined })"
      >
        {{ t('feed.hideDeleted') }}
      </Checkbox>
    </div>

    <div class="project__feed" :class="`project__feed--${view}`">
      <FeedPost v-for="post in feed.posts" :key="post.id" :post="post" :view="view" />
    </div>

    <Alert v-if="feed.failed" type="error" show-icon :message="t('feed.failed')" />
    <Spin v-else-if="feed.loading" class="project__spin" />
    <Empty
      v-else-if="!feed.posts.length"
      :description="filtered || filters.hideClosed ? t('feed.nothingFound') : t('feed.empty')"
    />

    <div v-if="feed.posts.length" class="project__pages">
      <Button v-if="feed.lastPage < feed.pages" :loading="feed.loading" @click="showMore">
        {{ t('feed.showMore') }}
      </Button>
      <Pagination
        v-if="feed.pages > 1"
        :current="feed.lastPage"
        :total="feed.total"
        :page-size="feed.perPage"
        :show-size-changer="false"
        @change="goToPage"
      />
    </div>

    <Modal
      v-model:open="settingsOpen"
      :title="t('projectSettings.title')"
      :footer="null"
      destroy-on-close
    >
      <ProjectSettingsForm :project="project" />
    </Modal>
  </section>

  <Spin v-else class="project__spin" />
</template>

<style scoped>
.project {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.project__cover {
  display: block;
  width: 100%;
  max-height: 220px;
  object-fit: cover;
  border-radius: 8px;
}

.project__head {
  display: flex;
  align-items: center;
  gap: 16px;
}

.project__logo {
  flex-shrink: 0;
  width: 72px;
  height: 72px;
  object-fit: cover;
  border-radius: 50%;
}

.project__names {
  flex: 1;
  min-width: 0;
}

.project__title {
  margin: 0;
  font-size: 30px;
  font-weight: 500;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.project__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  opacity: 0.65;
}

.project__toolbar,
.project__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.project__toolbar {
  /* Room for the app's header, which stays on screen, when the feed is scrolled back to its top. */
  scroll-margin-top: 80px;
}

.project__found {
  margin-left: auto;
  opacity: 0.65;
}

.project__select {
  width: 190px;
}

.project__feed {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.project__feed--tile {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (max-width: 640px) {
  .project__feed--tile {
    grid-template-columns: minmax(0, 1fr);
  }
}

.project__feed--list {
  gap: 0;
}

.project__pages {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.project__spin {
  display: block;
  margin: 32px auto;
}
</style>
