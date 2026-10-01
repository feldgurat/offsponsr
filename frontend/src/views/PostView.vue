<script setup lang="ts">
import {
  ArrowLeftOutlined,
  ClockCircleOutlined,
  LeftOutlined,
  LockOutlined,
  RightOutlined,
} from '@ant-design/icons-vue'
import { Alert, Button, Result, Spin, Tag } from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { api, ApiError } from '@/api/client'
import type { PostDetails } from '@/api/types'
import MediaAttachment from '@/components/MediaAttachment.vue'
import MediaAudio from '@/components/MediaAudio.vue'
import PostBadges from '@/components/PostBadges.vue'
import PostBody from '@/components/PostBody.vue'
import { useFormat } from '@/composables/format'
import { audioPlacedInText } from '@/post/content'
import { type FileEvent, useSyncStore } from '@/stores/sync'

const { t } = useI18n()
const { duration, postDate } = useFormat()
const route = useRoute()
const router = useRouter()
const sync = useSyncStore()

const post = ref<PostDetails | null>(null)
const status = ref<'loading' | 'ready' | 'missing' | 'error'>('loading')

const postId = computed(() => Number(route.params.id))

/** Counts the loads, so that the answer for a post already left is dropped. */
let generation = 0

async function load(quiet = false): Promise<void> {
  generation += 1
  const mine = generation
  if (!quiet) {
    status.value = 'loading'
    post.value = null
  }
  try {
    const fresh = await api.get<PostDetails>(`/posts/${postId.value}`)
    if (mine === generation) {
      post.value = fresh
      status.value = 'ready'
    }
  } catch (error) {
    if (mine === generation && !quiet) {
      status.value = error instanceof ApiError && error.status === 404 ? 'missing' : 'error'
    }
  }
}

watch(postId, () => void load(), { immediate: true })

/** One of this post's files is through: show the player in place of the button, or the reason. */
function onFile(event: FileEvent): void {
  const current = post.value
  if (current === null) {
    return
  }
  if (event.kind === 'media' && current.media.some((item) => item.id === event.id)) {
    void load(true)
  } else if (event.kind === 'post_cover' && event.id === current.id) {
    void load(true)
  }
}

let stopListening = () => {}
onMounted(() => {
  stopListening = sync.onFile(onFile)
})
onBeforeUnmount(() => stopListening())

const length = computed(() => {
  const current = post.value
  if (current === null) {
    return ''
  }
  const seconds =
    (current.duration_text ?? 0) + (current.duration_audio ?? 0) + (current.duration_video ?? 0)
  return seconds > 0 ? duration(seconds) : ''
})

const placedAudio = computed(() =>
  post.value ? audioPlacedInText(post.value.html, post.value.media) : new Set<number>(),
)
/** Audio without a place of its own in the text goes under it, as do the attached files. */
const audio = computed(
  () =>
    post.value?.media.filter((item) => item.kind === 'audio' && !placedAudio.value.has(item.id)) ??
    [],
)
const attachments = computed(() => post.value?.media.filter((item) => item.kind === 'attach') ?? [])

const needs = computed(() => {
  const level = post.value?.level
  if (!level) {
    return t('post.closedHint')
  }
  return level.price
    ? t('post.needsLevelPriced', { level: level.name, price: level.price.toLocaleString('ru') })
    : t('post.needsLevel', { level: level.name })
})

/** Back to the feed: to where it was left if the post was opened from it, to its top otherwise. */
function toProject(): void {
  const current = post.value
  if (current === null) {
    return
  }
  const back = window.history.state?.back
  if (typeof back === 'string' && back.startsWith(`/projects/${current.project.id}`)) {
    router.back()
  } else {
    void router.push({ name: 'project', params: { id: current.project.id } })
  }
}
</script>

<template>
  <Spin v-if="status === 'loading'" class="post__spin" />
  <Result v-else-if="status === 'missing'" status="404" :title="t('post.missing')">
    <template #extra>
      <RouterLink :to="{ name: 'library' }">
        <Button type="primary">{{ t('project.toLibrary') }}</Button>
      </RouterLink>
    </template>
  </Result>
  <Result v-else-if="status === 'error'" status="error" :title="t('post.failed')" />

  <article v-else-if="post" class="post">
    <Button type="link" class="post__back" @click="toProject">
      <template #icon><ArrowLeftOutlined /></template>
      {{ post.project.title }}
    </Button>

    <h1 class="post__title">{{ post.title }}</h1>
    <div class="post__meta">
      <span>{{ postDate(post.date) }}</span>
      <span v-if="length"><ClockCircleOutlined /> {{ length }}</span>
      <PostBadges :post="post" />
    </div>

    <Alert
      v-if="post.status === 'deleted_on_site'"
      type="warning"
      show-icon
      :message="t('post.deletedNotice')"
    />
    <Alert
      v-else-if="post.status === 'unavailable'"
      type="warning"
      show-icon
      :message="t('post.unavailableNotice')"
    />
    <Alert
      v-if="!post.closed && !post.text_is_full"
      type="info"
      show-icon
      :message="t('post.partialNotice')"
    />

    <div v-if="post.closed" class="post__closed">
      <img v-if="post.cover" class="post__closed-cover" :src="post.cover" alt="" />
      <LockOutlined class="post__lock" />
      <strong>{{ t('post.closedTitle') }}</strong>
      <span>{{ needs }}</span>
      <p v-if="post.excerpt" class="post__teaser">{{ post.excerpt }}</p>
    </div>

    <template v-else>
      <PostBody v-if="post.html" :html="post.html" :media="post.media" />

      <section v-if="audio.length" class="post__section">
        <h2 class="post__heading">{{ t('post.audio') }}</h2>
        <MediaAudio v-for="item in audio" :key="item.id" :media="item" />
      </section>

      <section v-if="attachments.length" class="post__section">
        <h2 class="post__heading">{{ t('post.attachments') }}</h2>
        <MediaAttachment v-for="item in attachments" :key="item.id" :media="item" />
      </section>
    </template>

    <div v-if="post.tags.length" class="post__tags">
      <Tag v-for="tag in post.tags" :key="tag.id">{{ tag.name }}</Tag>
    </div>

    <nav class="post__neighbours">
      <RouterLink
        v-if="post.newer"
        class="post__neighbour"
        :to="{ name: 'post', params: { id: post.newer.id } }"
      >
        <span class="post__direction"><LeftOutlined /> {{ t('post.newer') }}</span>
        <span>{{ post.newer.title }}</span>
      </RouterLink>
      <span v-else />
      <RouterLink
        v-if="post.older"
        class="post__neighbour post__neighbour--older"
        :to="{ name: 'post', params: { id: post.older.id } }"
      >
        <span class="post__direction">{{ t('post.older') }} <RightOutlined /></span>
        <span>{{ post.older.title }}</span>
      </RouterLink>
    </nav>
  </article>
</template>

<style scoped>
.post {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.post__spin {
  display: block;
  margin: 64px auto;
}

.post__back {
  align-self: flex-start;
  padding: 0;
}

.post__title {
  margin: 0;
  font-size: 30px;
  font-weight: 500;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.post__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
}

.post__meta > span:not(.post-badges) {
  opacity: 0.65;
}

.post__closed {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 24px;
  border: 1px solid var(--c-border, rgba(128, 128, 128, 0.25));
  border-radius: 8px;
  text-align: center;
}

.post__closed-cover {
  width: 100%;
  max-height: 320px;
  margin-bottom: 8px;
  object-fit: cover;
  border-radius: 6px;
  filter: brightness(0.6);
}

.post__lock {
  font-size: 32px;
  opacity: 0.65;
}

.post__teaser {
  margin: 8px 0 0;
  text-align: left;
}

.post__section {
  display: flex;
  flex-direction: column;
}

.post__heading {
  margin: 8px 0 4px;
  font-size: 18px;
  font-weight: 500;
}

.post__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 0;
}

.post__neighbours {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--c-border, rgba(128, 128, 128, 0.25));
}

.post__neighbour {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  color: inherit;
  overflow-wrap: anywhere;
}

.post__neighbour:hover {
  color: var(--c-primary, #fa541c);
}

.post__neighbour--older {
  align-items: flex-end;
  text-align: right;
}

.post__direction {
  font-size: 13px;
  opacity: 0.65;
}
</style>
